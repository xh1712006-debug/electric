import random
import time
from .models import RelayAutoCheckLog

def fetch_relay_parameters_from_api(relay):
    """
    Giả lập gọi API tới Rơ-le ngoài thực địa.
    Sẽ trả về 1 list dictionary chứa thông số.
    Thỉnh thoảng (20% xác suất) sẽ cố tình làm sai lệch 1-2 thông số để test.
    """
    time.sleep(0.5) # Giả lập network delay
    
    active_sheet = relay.active_sheet
    if not active_sheet or not active_sheet.extracted_data:
        return []
        
    db_params = active_sheet.extracted_data
    api_data = []
    
    should_mismatch = random.random() < 0.2 # 20% cơ hội bị sai lệch
    
    for param in db_params:
        # Bỏ qua các trường metadata không phải của rơ-le
        if param.get('parameter_code') in ['STATION_NAME', 'RELAY_CODE']:
            continue
            
        val = param.get('value', '')
        
        # Làm sai lệch dữ liệu
        if should_mismatch and random.random() < 0.3:
            try:
                numeric_val = float(val)
                val = str(round(numeric_val * 1.2, 2)) # Tăng 20%
                if val.endswith('.0'):
                    val = val[:-2]
            except ValueError:
                val = str(val) + "_err"
                
        api_data.append({
            'code': param.get('parameter_code', ''),
            'name': param.get('parameter_name', ''),
            'value': str(val)
        })
        
    return api_data

def compare_and_log_relay_check(relay):
    """Thực hiện check và lưu vào DB"""
    active_sheet = relay.active_sheet
    if not active_sheet or not active_sheet.extracted_data:
        return None
        
    api_data = fetch_relay_parameters_from_api(relay)
    
    # Tạo dict chứa các parameters từ DB để dễ so sánh
    db_params = {}
    for p in active_sheet.extracted_data:
        if p.get('parameter_code') not in ['STATION_NAME', 'RELAY_CODE']:
            db_params[p.get('parameter_code')] = str(p.get('value', ''))
    
    differences = []
    
    for api_param in api_data:
        code = api_param['code']
        api_val = api_param['value']
        db_val = db_params.get(code, '')
        
        is_diff = False
        try:
            if float(api_val) != float(db_val):
                is_diff = True
        except:
            if str(api_val).strip() != str(db_val).strip():
                is_diff = True
                
        # Gắn thêm cờ để template dễ render
        api_param['is_diff'] = is_diff
        api_param['db_value'] = db_val
                
        if is_diff:
            differences.append({
                'code': code,
                'name': api_param['name'],
                'db_value': db_val,
                'api_value': api_val
            })
                
    status = 'MISMATCH' if differences else 'MATCH'
    
    log = RelayAutoCheckLog.objects.create(
        relay=relay,
        status=status,
        api_raw_data=api_data,
        differences=differences
    )
    
    # Nếu có sai lệch, tạm ngưng lịch hẹn giờ
    if status == 'MISMATCH' and not relay.is_paused_for_correction:
        relay.is_paused_for_correction = True
        relay.paused_schedule_data = {
            'check_interval_value': relay.check_interval_value,
            'check_interval_unit': relay.check_interval_unit
        }
        relay.save(update_fields=['is_paused_for_correction', 'paused_schedule_data'])
    
    # Nếu dữ liệu đã khớp 100% và rơ-le đang bị tạm ngưng → tự động bật lại
    elif status == 'MATCH' and relay.is_paused_for_correction:
        relay.is_paused_for_correction = False
        
        # Khôi phục lịch hẹn giờ ban đầu nếu có lưu
        if relay.paused_schedule_data:
            relay.check_interval_value = relay.paused_schedule_data.get('check_interval_value', relay.check_interval_value)
            relay.check_interval_unit = relay.paused_schedule_data.get('check_interval_unit', relay.check_interval_unit)
            relay.paused_schedule_data = None
        
        from django.utils import timezone
        relay.last_checked_at = timezone.now()
        relay.next_check_at = relay.calculate_next_check(from_time=relay.last_checked_at)
        relay.save(update_fields=[
            'is_paused_for_correction', 'paused_schedule_data',
            'check_interval_value', 'check_interval_unit',
            'last_checked_at', 'next_check_at'
        ])
    
    # Broadcast via Channels to any user viewing the autocheck dashboard
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    if channel_layer:
        # We can trigger a generic notification to all admins, or a specific event for HTMX
        async_to_sync(channel_layer.group_send)(
            "autocheck_updates",
            {
                "type": "send_notification",
                "title": f"Cập nhật Rơ-le {relay.relay_code}",
                "message": f"Vừa hoàn tất đối chiếu tự động. Kết quả: {'Khớp' if status == 'MATCH' else 'Lệch'}",
                "level": "success" if status == 'MATCH' else "warning"
            }
        )
        
    return log
