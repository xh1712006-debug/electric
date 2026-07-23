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
    if not active_sheet:
        return []
        
    db_params = active_sheet.parameter_values.all()
    api_data = []
    
    should_mismatch = random.random() < 0.2 # 20% cơ hội bị sai lệch
    
    for param in db_params:
        val = param.value
        
        # Làm sai lệch dữ liệu
        if should_mismatch and random.random() < 0.3:
            try:
                numeric_val = float(val)
                val = str(round(numeric_val * 1.2, 2)) # Tăng 20%
                if val.endswith('.0'):
                    val = val[:-2]
            except ValueError:
                val = val + "_err"
                
        api_data.append({
            'code': param.setting.parameter_code,
            'name': param.setting.parameter_name,
            'value': val
        })
        
    return api_data

def compare_and_log_relay_check(relay):
    """Thực hiện check và lưu vào DB"""
    active_sheet = relay.active_sheet
    if not active_sheet:
        return None
        
    api_data = fetch_relay_parameters_from_api(relay)
    db_params = {p.setting.parameter_code: p.value for p in active_sheet.parameter_values.select_related('setting').all()}
    
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
    return log
