import os
from celery import Celery
from celery.signals import worker_ready

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')

app = Celery('rms_project')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

from celery.schedules import crontab

app.conf.beat_schedule = {
    'check-relays-every-minute': {
        'task': 'stations.tasks.schedule_due_autochecks',
        'schedule': crontab(minute='*'),  # Run every minute
    },
    'auto-sync-api-every-minute': {
        'task': 'core.tasks.check_and_run_auto_sync',
        'schedule': crontab(minute='*'),  # Run every minute to check if interval has elapsed
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@worker_ready.connect
def reset_stuck_processing_jobs(sender, **kwargs):
    """
    Khi Celery worker khởi động lại, chỉ reset các OcrJob đang ở trạng thái
    PROCESSING về FAILED — vì những task đó đang thực sự chạy và bị gián đoạn.
    Các job PENDING được giữ nguyên để Celery tiếp tục xử lý từ hàng đợi Redis.
    """
    try:
        import django
        django.setup()
    except RuntimeError:
        pass  # Django đã được setup rồi

    try:
        from sheets.models import OcrJob
        from django.core.cache import cache
        from sheets.tasks import broadcast_ocr_job_update

        # Chỉ reset PROCESSING (đang chạy thật) — KHÔNG đụng vào PENDING (đang xếp hàng)
        stuck_jobs = list(OcrJob.objects.filter(status='PROCESSING').select_related('sheet', 'sheet__created_by'))
        if not stuck_jobs:
            return

        for job in stuck_jobs:
            # Xóa cache flags để tránh stale data
            cache.delete(f"ocr_header_done_{job.id}")
            cache.delete(f"ocr_header_failed_{job.id}")
            cache.delete(f"ocr_header_data_{job.id}")
            # Đặt lại về FAILED để user biết và thử lại
            job.status = 'FAILED'
            job.error_detail = 'Tiến trình bị gián đoạn do khởi động lại hệ thống. Vui lòng bấm "Trích xuất lại" để tiếp tục.'
            job.save(update_fields=['status', 'error_detail'])
            try:
                broadcast_ocr_job_update(job=job, stage_text='Cần xử lý lại')
            except Exception:
                pass

        print(f"[RMS Startup] Đã reset {len(stuck_jobs)} job PROCESSING → FAILED do worker restart.")
    except Exception as exc:
        print(f"[RMS Startup] Không thể reset stuck jobs: {exc}")

