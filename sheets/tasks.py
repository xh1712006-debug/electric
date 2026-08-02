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

@shared_task(bind=True, max_retries=3)
def run_ocr_subprocess(self, job_id):
    import subprocess
    import json
    import os
    from django.conf import settings
    from sheets.models import OcrJob
    from pathlib import Path
    
    try:
        job = OcrJob.objects.get(id=job_id)
    except OcrJob.DoesNotExist:
        return "OcrJob not found"
        
    job.status = 'PROCESSING'
    job.save(update_fields=['status'])
    
    if not job.sheet.scan_file:
        job.status = 'FAILED'
        job.error_detail = 'No scan file found'
        job.save()
        return "No scan file"

    input_pdf = job.sheet.scan_file.path
    # Tạo thư mục output_root
    output_root = os.path.join(settings.MEDIA_ROOT, 'ocr_artifacts')
    os.makedirs(output_root, exist_ok=True)
    
    # Path tới python trong venv của OCR_PRJ (Local Windows) hoặc system python (Docker Linux)
    project_root = settings.BASE_DIR
    ocr_prj_root = os.path.join(project_root, 'OCR_PRJ')
    
    if os.name == 'nt':
        # Trên Windows, dùng venv riêng của OCR_PRJ nếu có
        python_exe = os.path.join(ocr_prj_root, '.venv', 'Scripts', 'python.exe')
    else:
        # Trên Linux/Docker, dùng python hệ thống vì tất cả đã cài chung trong image
        import sys
        python_exe = sys.executable
    
    if not os.path.exists(python_exe):
        job.status = 'FAILED'
        job.error_detail = f'OCR Python interpreter not found at {python_exe}'
        job.save()
        return "Python exe not found"

    # Xây dựng lệnh gọi CLI
    cmd = [
        python_exe, "-m", "src.relay_form_ocr",
        "--input", str(input_pdf),
        "--output-root", str(output_root),
        "--correlation-id", str(job.correlation_id),
        "--json"
    ]
    
    # Đặt PYTHONPATH để OCR_PRJ hoạt động được đúng
    env = os.environ.copy()
    env['PYTHONPATH'] = ocr_prj_root

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, encoding='utf-8')
        
        # Phân tích kết quả stdout JSON
        output_json = result.stdout.strip()
        if output_json:
            try:
                parsed_data = json.loads(output_json)
                job.result_data = parsed_data
                
                # Cập nhật status từ OcrResult
                result_status = parsed_data.get('status')
                review_status = parsed_data.get('review_status')
                job.review_status = review_status
                
                if result.returncode == 0:
                    if result_status == 'success_with_warnings':
                        job.status = 'SUCCESS_WITH_WARNINGS'
                    elif result_status == 'failed' or result_status == 'error':
                        job.status = 'FAILED'
                    else:
                        job.status = 'SUCCESS'
                        
                    if job.status != 'FAILED':
                        # Update SettingSheet extracted_data
                        if 'business' in parsed_data:
                            business = parsed_data['business']
                            if 'setting_records' in business:
                                job.sheet.extracted_data = business['setting_records']
                            
                            # Tự động gán metadata từ page1_fields
                            if 'page1_fields' in business:
                                page1 = business['page1_fields']
                                
                                # Cập nhật mã phiếu và tiêu đề
                                if 'ticket_number' in page1 and page1['ticket_number'].get('value'):
                                    ocr_sheet_code = page1['ticket_number']['value']
                                    # Kiểm tra xem mã này đã tồn tại chưa
                                    from sheets.models import SettingSheet
                                    if not SettingSheet.objects.filter(sheet_code=ocr_sheet_code).exclude(pk=job.sheet.pk).exists():
                                        job.sheet.sheet_code = ocr_sheet_code
                                        job.sheet.title = f"Phiếu {job.sheet.sheet_code}"
                                    else:
                                        job.sheet.title = f"Phiếu {ocr_sheet_code} (Bản phụ)"
                                
                                # Tìm và gán Station
                                if 'station' in page1 and page1['station'].get('value'):
                                    station_name_ocr = page1['station']['value']
                                    from stations.models import Station
                                    st = Station.objects.filter(station_name__icontains=station_name_ocr).first()
                                    if st:
                                        job.sheet.station = st
                                        
                                # Tìm và gán Relay
                                if 'relay_name' in page1 and page1['relay_name'].get('value'):
                                    relay_name_ocr = page1['relay_name']['value']
                                    from stations.models import Relay
                                    rl = Relay.objects.filter(relay_name__icontains=relay_name_ocr).first()
                                    if not rl:
                                        rl = Relay.objects.filter(relay_code__icontains=relay_name_ocr).first()
                                        
                                    if rl:
                                        job.sheet.relay = rl
                                        if rl.bay and not job.sheet.station:
                                            job.sheet.station = rl.bay.station
                            
                            job.sheet.save(update_fields=['extracted_data', 'sheet_code', 'title', 'station', 'relay'])
                    else:
                        if 'error' in parsed_data and parsed_data['error']:
                            job.error_code = parsed_data['error'].get('code')
                            job.error_stage = parsed_data['error'].get('stage')
                            job.error_detail = parsed_data['error'].get('message', 'AI Model reported failure.')
                        else:
                            job.error_detail = "AI Model trả về trạng thái thất bại nhưng không có mô tả lỗi."
                        
                else:
                    job.status = 'FAILED'
                    if 'error' in parsed_data and parsed_data['error']:
                        job.error_code = parsed_data['error'].get('code')
                        job.error_stage = parsed_data['error'].get('stage')
                        job.error_detail = f"Exit Code {result.returncode}. Lỗi hệ thống OCR."
                    else:
                        job.error_detail = result.stderr
            except json.JSONDecodeError:
                job.status = 'FAILED'
                job.error_detail = f"Không thể parse JSON từ OCR. RAW: {output_json[:200]}"
        else:
            job.status = 'FAILED'
            job.error_detail = f"OCR không trả về dữ liệu. Stderr: {result.stderr[:200]}"
            
        job.save()
        return job.status

    except Exception as e:
        job.status = 'FAILED'
        job.error_detail = str(e)
        job.save()
        # Nếu lỗi mạng hay tài nguyên (vd OOM), có thể retry
        raise self.retry(exc=e, countdown=60)
