with open('d:/project/dien-luc/stations/views.py', 'a', encoding='utf-8') as f:
    f.write('''
@login_required
def global_bulk_create(request):
    if request.method == 'POST':
        raw_text = request.POST.get('raw_text', '')
        lines = raw_text.strip().split('\\n')
        
        stations_cache = {}
        bays_cache = {}
        relays_to_create = []
        created_count = 0
        
        try:
            for line in lines:
                if not line.strip(): continue
                cols = line.split('\\t')
                if len(cols) < 5: continue
                
                s_code = cols[0].strip()
                s_name = cols[1].strip()
                b_code = cols[2].strip()
                b_name = cols[3].strip()
                r_code = cols[4].strip()
                r_name = cols[5].strip() if len(cols) > 5 else ''
                r_manuf = cols[6].strip() if len(cols) > 6 else ''
                
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
            
            Relay.objects.bulk_create(relays_to_create, ignore_conflicts=True)
            created_count = len(relays_to_create)
            messages.success(request, f"Đã nhập toàn hệ thống thành công! Tạo {created_count} Rơ-le mới.")
        except Exception as e:
            messages.error(request, f"Có lỗi xảy ra: {str(e)}")
            
    return redirect('station_list')
''')
