import re

with open('d:/project/dien-luc/stations/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Make sure openpyxl is imported
if 'import openpyxl' not in content:
    content = content.replace('import io\n', 'import io\nimport openpyxl\n')

new_global_func = '''@login_required
def global_bulk_create(request):
    if request.method == 'POST' and 'excel_file' in request.FILES:
        excel_file = request.FILES['excel_file']
        if not (excel_file.name.endswith('.xlsx') or excel_file.name.endswith('.xls')):
            messages.error(request, "Vui lòng tải lên file định dạng Excel (.xlsx hoặc .xls).")
            return redirect('station_list')
            
        stations_cache = {}
        bays_cache = {}
        relays_to_create = []
        created_count = 0
        
        try:
            wb = openpyxl.load_workbook(excel_file, data_only=True)
            sheet = wb.active
            
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i == 0: continue # Skip header
                if not row or len(row) < 5 or not row[0]: continue
                
                s_code = str(row[0]).strip()
                s_name = str(row[1]).strip() if row[1] else s_code
                b_code = str(row[2]).strip()
                b_name = str(row[3]).strip() if row[3] else b_code
                r_code = str(row[4]).strip()
                r_name = str(row[5]).strip() if len(row) > 5 and row[5] else ''
                r_manuf = str(row[6]).strip() if len(row) > 6 and row[6] else ''
                
                # Get or Create Station
                if s_code not in stations_cache:
                    station, _ = Station.objects.get_or_create(station_code=s_code, defaults={'station_name': s_name})
                    stations_cache[s_code] = station
                station = stations_cache[s_code]
                
                # Get or Create Bay
                cache_key = f"{s_code}_{b_code}"
                if cache_key not in bays_cache:
                    bay, _ = Bay.objects.get_or_create(station=station, bay_code=b_code, defaults={'bay_name': b_name})
                    bays_cache[cache_key] = bay
                bay = bays_cache[cache_key]
                
                # Add to relay list
                if r_code:
                    relays_to_create.append(Relay(bay=bay, relay_code=r_code, relay_name=r_name, manufacturer=r_manuf))
            
            if relays_to_create:
                Relay.objects.bulk_create(relays_to_create, ignore_conflicts=True)
                created_count = len(relays_to_create)
            
            messages.success(request, f"Đã nhập toàn hệ thống từ Excel thành công! Tạo mới {len(stations_cache)} Trạm, {len(bays_cache)} Ngăn lộ và {created_count} Rơ-le.")
        except Exception as e:
            messages.error(request, f"Có lỗi xảy ra khi đọc file Excel: {str(e)}")
            
    return redirect('station_list')'''

# Replace old global_bulk_create with new one
# Regex to match the old function from @login_required to the end of the file or next function
old_func_pattern = re.compile(r'@login_required\ndef global_bulk_create\(request\):.*?(?=@login_required|\Z)', re.DOTALL)
content = old_func_pattern.sub(new_global_func + '\n', content)

with open('d:/project/dien-luc/stations/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
