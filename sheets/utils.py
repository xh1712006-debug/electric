from .models import SettingSheet

def update_has_parameters_changed_for_sheet(sheet):
    """
    So sánh thông số của phiếu hiện tại với phiếu trước đó (của cùng một rơ-le).
    Cập nhật cờ has_parameters_changed = True nếu có thay đổi.
    """
    if not sheet.relay or not sheet.extracted_data:
        if sheet.has_parameters_changed:
            sheet.has_parameters_changed = False
            sheet.save(update_fields=['has_parameters_changed'])
        return False

    previous_sheet = SettingSheet.objects.filter(
        relay=sheet.relay,
        created_at__lt=sheet.created_at
    ).order_by('-created_at').first()

    if not previous_sheet:
        # Nếu không có phiếu trước đó, coi như không thay đổi (hoặc tuỳ logic business, ở đây theo logic cũ là không thêm vào list updated)
        has_diff = False
    else:
        old_data = previous_sheet.extracted_data or []
        new_data = sheet.extracted_data or []
        
        old_dict = {item.get('parameter_code'): item for item in old_data if item.get('parameter_code')}
        new_dict = {item.get('parameter_code'): item for item in new_data if item.get('parameter_code')}
        
        has_diff = False
        for code, new_item in new_dict.items():
            if code not in old_dict:
                has_diff = True
                break
            else:
                try:
                    old_val = float(old_dict[code].get('value', 0))
                    new_val = float(new_item.get('value', 0))
                    if old_val != new_val:
                        has_diff = True
                        break
                except (ValueError, TypeError):
                    if str(old_dict[code].get('value')) != str(new_item.get('value')):
                        has_diff = True
                        break
        
        if not has_diff:
            for code in old_dict:
                if code not in new_dict:
                    has_diff = True
                    break

    if sheet.has_parameters_changed != has_diff:
        sheet.has_parameters_changed = has_diff
        sheet.save(update_fields=['has_parameters_changed'])
        
    return has_diff
