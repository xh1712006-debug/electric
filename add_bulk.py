with open('d:/project/dien-luc/stations/views.py', 'a', encoding='utf-8') as f:
    f.write('''
@login_required
def relay_bulk_create(request, bay_id):
    if request.method == 'POST':
        bay = get_object_or_404(Bay, pk=bay_id)
        created_count = 0
        
        # Xử lý File Upload (CSV)
        if 'csv_file' in request.FILES:
            csv_file = request.FILES['csv_file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, "Vui lòng tải lên file định dạng CSV.")
                return redirect('station_list')
                
            try:
                decoded_file = csv_file.read().decode('utf-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string, delimiter=',')
                relays_to_create = []
                for idx, row in enumerate(reader):
                    if idx == 0: continue
                    if len(row) >= 1 and row[0].strip():
                        r_code = row[0].strip()
                        r_name = row[1].strip() if len(row) > 1 else ''
                        r_manuf = row[2].strip() if len(row) > 2 else ''
                        relays_to_create.append(Relay(bay=bay, relay_code=r_code, relay_name=r_name, manufacturer=r_manuf))
                
                Relay.objects.bulk_create(relays_to_create, ignore_conflicts=True)
                created_count = len(relays_to_create)
            except Exception as e:
                messages.error(request, f"Lỗi đọc file CSV: {str(e)}")
                return redirect('station_list')

        # Xử lý Paste Text (Raw Text)
        elif 'raw_text' in request.POST:
            raw_text = request.POST.get('raw_text', '')
            relays_to_create = []
            lines = raw_text.strip().split('\\n')
            for line in lines:
                if not line.strip(): continue
                cols = line.split('\\t')
                r_code = cols[0].strip()
                r_name = cols[1].strip() if len(cols) > 1 else ''
                r_manuf = cols[2].strip() if len(cols) > 2 else ''
                if r_code:
                    relays_to_create.append(Relay(bay=bay, relay_code=r_code, relay_name=r_name, manufacturer=r_manuf))
            
            Relay.objects.bulk_create(relays_to_create, ignore_conflicts=True)
            created_count = len(relays_to_create)
            
        messages.success(request, f"Đã nhập thành công {created_count} Rơ-le vào ngăn lộ {bay.bay_code}.")
    return redirect('station_list')
''')
