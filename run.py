import subprocess
import sys
import os

def main():
    print("==================================================")
    print("Bắt đầu khởi động Django Server & Celery Worker...")
    print("==================================================")
    
    # Đường dẫn đến file python và celery trong môi trường ảo
    python_exe = sys.executable
    celery_exe = os.path.join(os.path.dirname(python_exe), 'celery')

    if os.name == 'nt': # Windows
        celery_exe = celery_exe + '.exe'

    # 1. Chạy Máy chủ Web (Django)
    django_process = subprocess.Popen([python_exe, 'manage.py', 'runserver'])
    
    # 2. Chạy Công nhân xử lý ngầm (Celery)
    celery_process = subprocess.Popen([celery_exe, '-A', 'rms_project', 'worker', '--pool=solo', '-l', 'info'])
    
    try:
        # Giữ script chạy liên tục và in log của cả 2 ra màn hình
        django_process.wait()
        celery_process.wait()
    except KeyboardInterrupt:
        print("\nĐang tắt hệ thống...")
        django_process.terminate()
        celery_process.terminate()
        print("Đã tắt an toàn!")

if __name__ == '__main__':
    main()
