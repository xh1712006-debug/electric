import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rms_project.settings')
django.setup()

from sheets.models import SettingSheet

s = SettingSheet.objects.get(pk=7)
data = s.extracted_data or []

bases = [
    ('I_sc', 'Dòng ngắn mạch', 'A', 500, 2000), 
    ('V_nom', 'Điện áp định mức', 'V', 110, 220), 
    ('F_nom', 'Tần số', 'Hz', 49, 51), 
    ('Z_line', 'Tổng trở đường dây', 'Ohm', 10, 100), 
    ('P_active', 'Công suất tác dụng', 'MW', 50, 300), 
    ('Q_react', 'Công suất phản kháng', 'MVAR', 10, 150)
]

for i in range(1, 101):  # Generate 100 parameters
    b = random.choice(bases)
    conf = random.uniform(85.0, 99.9)
    data.append({
        'parameter_code': f'{b[0]}_{i}',
        'parameter_name': f'{b[1]} (Zone {i%3 + 1})',
        'unit': b[2],
        'value': round(random.uniform(b[3], b[4]), 2),
        'confidence': round(conf, 1)
    })

s.extracted_data = data
s.save()
print(f'Added 100 parameters to sheet {s.pk}. Total: {len(s.extracted_data)}')
