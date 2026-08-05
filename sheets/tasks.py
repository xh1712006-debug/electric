from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
import time
import uuid

@shared_task
def execute_bulk_create_task(idempotency_key, user_id, sheet_ids):
    from sheets.models import SettingSheet
    from django.contrib.auth.models import User
    from sheets.views import perform_mock_ocr
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        cache.set(idempotency_key, {'status': 'ERROR', 'message': 'User not found'}, timeout=86400)
        return

    success_count = 0
    failed_count = 0
    
    channel_layer = get_channel_layer()

    for sheet_id in sheet_ids:
        try:
            sheet = SettingSheet.objects.get(id=sheet_id)
            file_name = sheet.title
            
            # Gửi thông báo đang bắt đầu xử lý file này
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "file_name": file_name,
                        "status": "processing"
                    }
                )

            # Perform OCR on the uploaded file
            perform_mock_ocr(sheet)
            # Update status to ISSUED (Chờ rà soát)
            sheet.status = 'ISSUED'
            sheet.save(update_fields=['status'])
            success_count += 1
            # Simulate OCR processing delay
            time.sleep(2)
            
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "file_name": file_name,
                        "status": "success",
                        "processed_count": success_count + failed_count,
                        "total": len(sheet_ids)
                    }
                )
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "bulk_progress",
                        "event_type": "update_badges"
                    }
                )
        except Exception as e:
            failed_count += 1
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        "type": "send_notification",
                        "event_type": "bulk_progress",
                        "idempotency_key": idempotency_key,
                        "sheet_id": sheet_id,
                        "status": "failed",
                        "processed_count": success_count + failed_count,
                        "total": len(sheet_ids)
                    }
                )

    result_data = {
        'status': 'COMPLETED',
        'total_requested': len(sheet_ids),
        'success': success_count,
        'failed': failed_count,
        'finished_at': timezone.now().isoformat()
    }

    # Lưu kết quả vào Redis giữ trong 24h
    cache.set(idempotency_key, result_data, timeout=86400)
    
    # Gửi thông báo WebSocket tới User
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_notification",
                "title": "Trích xuất Hàng loạt Hoàn tất",
                "message": f"Đã xử lý xong {len(sheet_ids)} file. Thành công: {success_count}, Thất bại: {failed_count}.",
                "level": "success" if failed_count == 0 else "warning"
            }
        )


def _run_ocr_cli(input_pdf, output_root, correlation_id, stage="all", device_mode="CPU",
                  ws_callback=None):
    """
    Chạy OCR CLI subprocess và tuỳ chọn gọi ws_callback(page_no, total_pages, msg) khi có
    thông báo tiến trình từng trang từ stderr.

    Trả về: (returncode, data_dict, stderr_str)
    """
    import subprocess
    import json
    import os
    import sys
    import threading
    import tempfile
    from django.conf import settings

    project_root = settings.BASE_DIR
    ocr_prj_root = os.path.join(project_root, 'OCR_PRJ')

    # ── Chọn đúng Python interpreter ──────────────────────────────────────────
    if os.name == 'nt':
        python_exe = os.path.join(ocr_prj_root, '.venv', 'Scripts', 'python.exe')
    else:
        python_exe = sys.executable

    if not os.path.exists(python_exe):
        return -1, None, f"Không tìm thấy Python OCR tại {python_exe}"

    # Dùng file tạm để nhận JSON output — tránh hoàn toàn vấn đề pipe deadlock
    # khi nhiều job chạy song song (orphaned PaddleOCR child processes giữ pipe mở).
    result_fd, result_path = tempfile.mkstemp(suffix='.json', prefix=f'ocr_{correlation_id}_')
    os.close(result_fd)

    cmd = [
        python_exe, "-m", "src.relay_form_ocr",
        "--input", str(input_pdf),
        "--output-root", str(output_root),
        "--correlation-id", f"{correlation_id}_{stage}",
        "--stage", stage,
        "--json",
        "--output-json", result_path,
        "--overwrite-result",
    ]
    if device_mode == 'GPU':
        cmd.append("--gpu")

    env = os.environ.copy()
    env['PYTHONPATH'] = ocr_prj_root
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    # ── Chạy subprocess, đọc stderr theo từng dòng để bắt tiến trình trang ───
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,   # stdout không dùng nữa (kết quả ở file)
        stderr=subprocess.PIPE,
        cwd=ocr_prj_root,
        env=env,
        encoding='utf-8',
        errors='replace',
    )

    stderr_lines = []
    def _read_stderr():
        """Đọc toàn bộ stderr; gọi ws_callback khi thấy dòng tiến trình trang."""
        import re
        page_re = re.compile(r'trang\s+(\d+)/(\d+)', re.IGNORECASE)
        for line in proc.stderr:
            line = line.rstrip('\n')
            stderr_lines.append(line)
            if ws_callback:
                m = page_re.search(line)
                if m:
                    try:
                        ws_callback(int(m.group(1)), int(m.group(2)), line)
                    except Exception:
                        pass

    t_stderr = threading.Thread(target=_read_stderr, daemon=True)
    t_stderr.start()

    proc.wait()
    t_stderr.join(timeout=5)

    # Đọc kết quả từ file — không bị ảnh hưởng bởi orphaned child processes
    data = None
    try:
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            with open(result_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception:
        pass
    finally:
        try:
            os.unlink(result_path)
        except Exception:
            pass

    return proc.returncode, data, '\n'.join(stderr_lines)



def _safe_send_ws(channel_layer, user_id, payload):
    if channel_layer and user_id:
        try:
            async_to_sync(channel_layer.group_send)(f"user_{user_id}", payload)
        except Exception:
            pass


def broadcast_ocr_job_update(job=None, job_id=None, stage_text=None):
    """
    Phát sóng sự kiện cập nhật tiến trình OCR qua WebSocket (Django Channels)
    đến toàn bộ client trong group 'ocr_updates' theo thời gian thực.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from django.core.cache import cache
    from sheets.models import OcrJob

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    if job is None and job_id is not None:
        try:
            job = OcrJob.objects.select_related('sheet', 'sheet__created_by').get(id=job_id)
        except OcrJob.DoesNotExist:
            return

    if not job:
        return

    if stage_text:
        cache.set(f"ocr_stage_{job.id}", stage_text, timeout=86400)
    else:
        stage_text = cache.get(f"ocr_stage_{job.id}") or ''

    failed_count = OcrJob.objects.filter(status='FAILED').count()
    processing_count = OcrJob.objects.filter(status__in=['PENDING', 'PROCESSING']).count()
    success_count = OcrJob.objects.filter(status__in=['SUCCESS', 'SUCCESS_WITH_WARNINGS']).count()
    total_count = OcrJob.objects.count()

    job_data = {
        'id': job.id,
        'sheet_id': job.sheet.id if job.sheet else None,
        'sheet_code': job.sheet.sheet_code if job.sheet else f"Job#{job.id}",
        'sheet_title': job.sheet.title if job.sheet else '',
        'created_by': (
            job.sheet.created_by.get_full_name() or job.sheet.created_by.username
            if job.sheet and job.sheet.created_by else "Hệ thống"
        ),
        'device_mode': getattr(job, 'device_mode', 'CPU') or 'CPU',
        'status': job.status,
        'created_at_date': job.created_at.strftime('%d/%m/%Y') if job.created_at else '',
        'created_at_time': job.created_at.strftime('%H:%M:%S') if job.created_at else '',
        'error_code': job.error_code or '',
        'error_stage': job.error_stage or '',
        'error_detail': job.error_detail or '',
        'stage_text': stage_text or '',
    }

    event_payload = {
        'type': 'ocr_event',
        'event_type': 'ocr_update',
        'job': job_data,
        'stats': {
            'total': min(total_count, 50),
            'actual_total': total_count,
            'success': success_count,
            'processing': processing_count,
            'failed': failed_count,
        }
    }

    try:
        async_to_sync(channel_layer.group_send)("ocr_updates", event_payload)
    except Exception:
        pass


def _notify_page_progress(channel_layer, user_id, sheet_code, page_no, total_pages, stage_label):
    """Gửi thông báo WebSocket tiến trình bóc tách từng trang."""
    # Đã tắt thông báo popup để tránh spam màn hình khi xử lý nhiều phiếu
    pass

import threading

# Lock toàn cục để đảm bảo chỉ có tối đa 1 tiến trình Pipeline 1 và 1 tiến trình Pipeline 2 chạy cùng lúc (chống OOM)
_pipeline1_lock = threading.Lock()
_pipeline2_lock = threading.Lock()

def _pipeline_header_worker(job_ids, user_id=None, device_mode='CPU'):
    """
    Pipeline 1 (chạy ngầm song song):
    Với mỗi file, bóc tách tuần tự Trang 1 rồi Trang 2 (theo thứ tự).
    Sau khi bóc tách xong Trang 1 & 2, cập nhật thông tin phiếu (Mã phiếu, trạm, thiết bị),
    đánh dấu cache `ocr_header_done_{job_id} = True` để Pipeline 2 tiếp quản xử lý Trang 3+,
    sau đó Pipeline 1 chuyển sang bóc tách Trang 1 & 2 của file tiếp theo.
    """
    from django.db import connection
    from django.conf import settings
    from sheets.models import OcrJob, SettingSheet
    from stations.models import Station, Relay
    import os

    output_root = os.path.join(settings.MEDIA_ROOT, 'ocr_artifacts')
    os.makedirs(output_root, exist_ok=True)
    channel_layer = get_channel_layer()

    for job_id in job_ids:
        # ── Xóa cache cũ từ lần chạy trước (phòng flag stale gây lỗi) ─────────────
        cache.delete(f"ocr_header_done_{job_id}")
        cache.delete(f"ocr_header_failed_{job_id}")
        cache.delete(f"ocr_header_data_{job_id}")

        connection.close()
        try:
            job = OcrJob.objects.select_related('sheet', 'sheet__created_by').get(id=job_id)
        except OcrJob.DoesNotExist:
            cache.set(f"ocr_header_done_{job_id}", True, timeout=86400)
            cache.set(f"ocr_header_failed_{job_id}", True, timeout=86400)
            continue

        # ── Lấy đường dẫn file PDF ────────────────────────────────────────────
        input_pdf = None
        if job.sheet and job.sheet.scan_file:
            try:
                input_pdf = job.sheet.scan_file.path
            except Exception:
                input_pdf = str(job.sheet.scan_file)

        if not input_pdf or not os.path.exists(input_pdf):
            job.status = 'FAILED'
            job.error_detail = 'Không tìm thấy file scan PDF đính kèm.'
            job.save(update_fields=['status', 'error_detail'])
            broadcast_ocr_job_update(job=job, stage_text='Thiếu file scan PDF')
            cache.set(f"ocr_header_failed_{job_id}", True, timeout=86400)
            cache.set(f"ocr_header_done_{job_id}", True, timeout=86400)
            continue

        job.status = 'PROCESSING'
        job.sheet.status = 'DRAFT'
        job.sheet.save(update_fields=['status'])
        job.save(update_fields=['status'])
        broadcast_ocr_job_update(job=job, stage_text='Đang bóc tách Trang 1/2 (Thông tin chung)...')

        sheet_code = job.sheet.sheet_code or f"Job#{job_id}"

        # ── Thông báo bắt đầu Pipeline 1 ─────────────────────────────────────
        # Đã tắt thông báo popup

        # ── Định nghĩa callback cập nhật tiến trình trang ─────────────────────
        def _page_cb(page_no, total_pages, _msg, _chl=channel_layer, _uid=user_id,
                     _sc=sheet_code, _jb=job):
            _notify_page_progress(_chl, _uid, _sc, page_no, total_pages,
                                   f"Trang {page_no}/{total_pages} (Thông tin chung)")
            broadcast_ocr_job_update(job=_jb, stage_text=f"Đang bóc tách Trang {page_no}/{total_pages} (Thông tin chung)...")

        # ── Gọi OCR CLI cho stage=header (Trang 1 & 2 theo thứ tự) ───────────
        ret_code, data, stderr = _run_ocr_cli(
            input_pdf, output_root, job.correlation_id,
            stage="header", device_mode=device_mode,
            ws_callback=_page_cb,
        )

        if ret_code != 0 or not data or data.get('status') not in ('success', 'success_with_warnings'):
            job.status = 'FAILED'
            err_msg = (
                (data.get('error', {}).get('message') if data and 'error' in data else None)
                or stderr or f"Lỗi OCR Header (Exit Code {ret_code})"
            )
            job.error_detail = err_msg
            job.save(update_fields=['status', 'error_detail'])
            broadcast_ocr_job_update(job=job, stage_text='Lỗi bóc tách Trang 1 & 2')
            cache.set(f"ocr_header_failed_{job_id}", True, timeout=86400)
            cache.set(f"ocr_header_done_{job_id}", True, timeout=86400)

            _safe_send_ws(channel_layer, user_id, {
                "type": "send_notification",
                "title": "Lỗi bóc tách Trang 1 & 2",
                "message": f"Không thể trích xuất thông tin chung của phiếu {sheet_code}: {err_msg[:150]}",
                "level": "error",
            })
            _safe_send_ws(channel_layer, user_id, {"type": "bulk_progress", "event_type": "update_badges"})
            continue

        # ── Cập nhật thông tin phiếu từ kết quả Trang 1 ──────────────────────
        business = data.get('business', {})
        page1 = business.get('page1_fields', {})

        if 'ticket_number' in page1 and page1['ticket_number'].get('value'):
            ocr_sheet_code = page1['ticket_number']['value']
            if not SettingSheet.objects.filter(sheet_code=ocr_sheet_code).exclude(pk=job.sheet.pk).exists():
                job.sheet.sheet_code = ocr_sheet_code
                job.sheet.title = f"Phiếu {job.sheet.sheet_code}"
            else:
                job.sheet.title = f"Phiếu {ocr_sheet_code} (Bản phụ)"
            sheet_code = job.sheet.sheet_code

        if 'station' in page1 and page1['station'].get('value'):
            station_name_ocr = page1['station']['value']
            st = Station.objects.filter(station_name__icontains=station_name_ocr).first()
            if st:
                job.sheet.station = st

        if 'relay_name' in page1 and page1['relay_name'].get('value'):
            relay_name_ocr = page1['relay_name']['value']
            rl = Relay.objects.filter(relay_name__icontains=relay_name_ocr).first()
            if not rl:
                rl = Relay.objects.filter(relay_code__icontains=relay_name_ocr).first()
            if rl:
                job.sheet.relay = rl
                if rl.bay and not job.sheet.station:
                    job.sheet.station = rl.bay.station

        job.sheet.status = 'ISSUED'   # Chuyển sang Chờ rà soát ngay sau Trang 1 & 2
        job.sheet.save()
        cache.set(f"ocr_header_data_{job_id}", data, timeout=86400)
        cache.set(f"ocr_header_done_{job_id}", True, timeout=86400)

        # ── Thông báo Pipeline 1 hoàn tất, Pipeline 2 được giải phóng ─────────
        broadcast_ocr_job_update(job=job, stage_text='Hoàn thành thông tin chung, đang chờ bóc tách bảng thông số...')
        _safe_send_ws(channel_layer, user_id, {"type": "bulk_progress", "event_type": "update_badges"})


def _pipeline_details_worker(job_ids, user_id=None, device_mode='CPU'):
    """
    Pipeline 2 (chạy ngầm song song):
    Chờ Pipeline 1 hoàn thành Trang 1 & 2 của từng file, sau đó bóc tách tuần tự
    Trang 3 → Trang 4 → Trang 5 → ... theo thứ tự.
    Sau khi hoàn tất, cập nhật bảng thông số và chuyển phiếu sang Chờ rà soát.
    """
    from django.db import connection
    from django.conf import settings
    from sheets.models import OcrJob
    from sheets.utils import update_has_parameters_changed_for_sheet
    import os

    output_root = os.path.join(settings.MEDIA_ROOT, 'ocr_artifacts')
    os.makedirs(output_root, exist_ok=True)
    channel_layer = get_channel_layer()

    with _pipeline2_lock:
        for job_id in job_ids:
            # ── Đợi Pipeline 1 hoàn tất file này (timeout 10 phút) ───────────────
            wait_start = time.time()
            while not cache.get(f"ocr_header_done_{job_id}"):
                if time.time() - wait_start > 600:
                    # Hết timeout: Pipeline 1 có thể bị chết — đánh dấu FAILED rõ ràng
                    connection.close()
                    try:
                        stuck_job = OcrJob.objects.select_related('sheet').get(id=job_id)
                        if stuck_job.status == 'PROCESSING':
                            stuck_job.status = 'FAILED'
                            stuck_job.error_detail = 'Pipeline 1 (Header) timeout sau 10 phút. Có thể do Celery khởi động lại giữa chừng. Hãy thử lại.'
                            stuck_job.save(update_fields=['status', 'error_detail'])
                            broadcast_ocr_job_update(job=stuck_job, stage_text='Timeout — Thử lại')
                            _safe_send_ws(channel_layer, user_id, {
                                "type": "bulk_progress",
                                "event_type": "update_badges"
                            })
                    except Exception:
                        pass
                    break
                time.sleep(0.5)
    
            # Nếu Pipeline 1 báo lỗi → bỏ qua file này
            if cache.get(f"ocr_header_failed_{job_id}"):
                continue
    
            connection.close()
            try:
                job = OcrJob.objects.select_related('sheet', 'sheet__created_by').get(id=job_id)
            except OcrJob.DoesNotExist:
                continue
    
            input_pdf = None
            if job.sheet and job.sheet.scan_file:
                try:
                    input_pdf = job.sheet.scan_file.path
                except Exception:
                    input_pdf = str(job.sheet.scan_file)
    
            if not input_pdf or not os.path.exists(input_pdf):
                job.status = 'FAILED'
                job.error_detail = 'Không tìm thấy file scan PDF (Pipeline 2).'
                job.save(update_fields=['status', 'error_detail'])
                broadcast_ocr_job_update(job=job, stage_text='Thiếu file PDF ở Pipeline 2')
                _safe_send_ws(channel_layer, user_id, {"type": "bulk_progress", "event_type": "update_badges"})
                continue
    
            sheet_code = job.sheet.sheet_code or f"Job#{job_id}"
            page_count = 0
            try:
                import fitz
                with fitz.open(input_pdf) as doc:
                    page_count = len(doc)
            except Exception:
                pass
                
            if page_count > 0:
                stage_txt = f'Đang khởi tạo OCR (Trang 3/{page_count})...'
            else:
                stage_txt = 'Đang khởi tạo OCR (Trang 3+)...'
                
            broadcast_ocr_job_update(job=job, stage_text=stage_txt)
    
            # ── Định nghĩa callback cập nhật tiến trình trang ─────────────────────
            def _page_cb(page_no, total_pages, _msg, _chl=channel_layer, _uid=user_id,
                         _sc=sheet_code, _jb=job):
                _notify_page_progress(_chl, _uid, _sc, page_no, total_pages,
                                       f"Trang {page_no}/{total_pages} (Bảng thông số)")
                broadcast_ocr_job_update(job=_jb, stage_text=f"Đang bóc tách Trang {page_no}/{total_pages} (Bảng thông số)...")
    
            # ── Gọi OCR CLI cho stage=details (Trang 3+ theo thứ tự) ──────────────
            ret_code, data, stderr = _run_ocr_cli(
                input_pdf, output_root, job.correlation_id,
                stage="details", device_mode=device_mode,
                ws_callback=_page_cb,
            )
    
            header_data = cache.get(f"ocr_header_data_{job_id}") or {}
    
            if ret_code != 0 or not data or data.get('status') not in ('success', 'success_with_warnings'):
                job.status = 'FAILED'
                job.sheet.status = 'DRAFT'
                job.sheet.save(update_fields=['status'])
                err_msg = (
                    (data.get('error', {}).get('message') if data and 'error' in data else None)
                    or stderr or f"Lỗi OCR Details (Exit Code {ret_code})"
                )
                job.error_detail = err_msg
                job.save(update_fields=['status', 'error_detail'])
                broadcast_ocr_job_update(job=job, stage_text='Lỗi bóc tách Bảng thông số')
    
                _safe_send_ws(channel_layer, user_id, {
                    "type": "send_notification",
                    "title": "Lỗi bóc tách Bảng thông số",
                    "message": f"Không thể xử lý bảng thông số phiếu {sheet_code}: {err_msg[:150]}",
                    "level": "error",
                })
                _safe_send_ws(channel_layer, user_id, {"type": "bulk_progress", "event_type": "update_badges"})
                continue
    
            # ── Bóc tách thành công — lưu bảng thông số vào phiếu ────────────────
            business = data.get('business', {})
            setting_records = business.get('setting_records', [])
            note_candidates = business.get('note_candidates', [])
    
            job.sheet.extracted_data = setting_records
            update_has_parameters_changed_for_sheet(job.sheet)
            # Không đổi status nữa vì đã ISSUED ở Pipeline 1. Chỉ lưu update_fields 
            # để tránh ghi đè thông tin phân công (assigned_to) nếu user đang thao tác
            job.sheet.save(update_fields=['extracted_data'])
    
            job.status = 'SUCCESS'
            job.review_status = 'COMPLETED'
            job.result_data = {
                'status': 'success',
                'business': {
                    'page1_fields': header_data.get('business', {}).get('page1_fields', {}),
                    'important_source_labels': header_data.get('business', {}).get('important_source_labels', {}),
                    'important_field_resolution': header_data.get('business', {}).get('important_field_resolution', {}),
                    'setting_records': setting_records,
                    'note_candidates': note_candidates,
                },
                'summary': {
                    **header_data.get('summary', {}),
                    **data.get('summary', {}),
                },
                'pages': (header_data.get('pages', []) or []) + (data.get('pages', []) or []),
            }
            job.save()
            broadcast_ocr_job_update(job=job, stage_text='Đã hoàn thành ✓')
    
            # ── Thông báo hoàn tất toàn bộ phiếu ─────────────────────────────────
            _safe_send_ws(channel_layer, user_id, {"type": "bulk_progress", "event_type": "update_badges"})
    

@shared_task
def execute_parallel_ocr_batch(job_ids, user_id=None, device_mode='CPU'):
    """
    Điều phối 2 Pipeline OCR chạy song song ngầm:
      - Pipeline 1: Bóc tách Trang 1 → Trang 2 theo thứ tự cho từng file.
      - Pipeline 2: Đi theo sau, chờ Pipeline 1 bóc tách xong file nào thì bóc Trang 3+ của file đó.
    """
    import concurrent.futures
    import logging
    logger = logging.getLogger(__name__)

    if not isinstance(job_ids, list):
        job_ids = [job_ids]

    logger.info("[OCR Batch] Bắt đầu xử lý %d job(s) qua 2 luồng Pipeline song song", len(job_ids))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_header  = executor.submit(_pipeline_header_worker,  job_ids, user_id, device_mode)
        f_details = executor.submit(_pipeline_details_worker, job_ids, user_id, device_mode)
        
        for future in (f_header, f_details):
            try:
                future.result()
            except Exception as exc:
                logger.exception(
                    "[OCR Batch] Pipeline worker raised an exception: %s", exc
                )

    logger.info("[OCR Batch] Hoàn thành %d job(s)", len(job_ids))
    return f"Processed batch of {len(job_ids)} OCR jobs via 2 parallel pipelines"



@shared_task(bind=True, max_retries=3)
def run_ocr_subprocess(self, job_id):
    """Task đơn lẻ tương thích ngược: kích hoạt qua luồng 2 pipeline song song."""
    from sheets.models import OcrJob
    try:
        job = OcrJob.objects.select_related('sheet', 'sheet__created_by').get(id=job_id)
        user_id = job.sheet.created_by.id if job.sheet.created_by else None
        device_mode = getattr(job, 'device_mode', 'CPU')
        return execute_parallel_ocr_batch(job_ids=[job_id], user_id=user_id, device_mode=device_mode)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
