import json
import urllib.request
import requests
from urllib.parse import urlparse
import logging
from core.models import SystemConfig
from categories.models import ManagementUnit, ManufacturingCountry, Manufacturer, Ownership, VoltageLevel, EquipmentType, OperationalStatus, Line, Project, Location
from stations.models import Bay, Relay, Station
from core.utils.xml_converter import json_to_xml
import traceback
from link_data import run_linking

logger = logging.getLogger(__name__)

def run_api_sync(config_key=None, config_id=None):
    """
    Chạy quá trình đồng bộ cho một SystemConfig cụ thể.
    Trả về (success: bool, count: int, error_message: str)
    """
    try:
        if config_id:
            config = SystemConfig.objects.get(id=config_id)
        elif config_key:
            config = SystemConfig.objects.get(key=config_key)
        else:
            return False, 0, "No config identified"
    except SystemConfig.DoesNotExist:
        return False, 0, "Config not found"

    url = config.value
    if not url or not url.startswith('http'):
        return False, 0, "URL không hợp lệ"
        
    try:
        # Tự động ép dùng HTTPS vì tường lửa Cloudrity chặn cổng HTTP (80)
        if url.startswith('http://') and 'pmis.npt.com.vn' in url:
            url = url.replace('http://', 'https://', 1)
            
        parsed_url = urlparse(url)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Host': parsed_url.hostname
        }
        if config.auth_header:
            auth_val = config.auth_header.strip()
            # Tự động nhận diện Username:Password để chuyển thành Basic Auth
            if ':' in auth_val and not auth_val.lower().startswith('basic ') and not auth_val.lower().startswith('bearer '):
                import base64
                encoded = base64.b64encode(auth_val.encode('utf-8')).decode('utf-8')
                headers['Authorization'] = f'Basic {encoded}'
            else:
                headers['Authorization'] = auth_val
            
        # Force direct connection bypassing proxy, ignore SSL errors if any
        sess = requests.Session()
        sess.trust_env = False # Ignore HTTP_PROXY environment variables
        res = sess.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status()
        response_text = res.text
    except Exception as e:
        return False, 0, f"Lỗi kết nối ({type(e).__name__}): {str(e)}"
        
    try:
        data_json = json.loads(response_text)
    except json.JSONDecodeError:
        return False, 0, "API không trả về định dạng JSON."
        
    # Extract list data
    lst_data = []
    if isinstance(data_json, list) and len(data_json) > 0 and 'lst' in data_json[0]:
        lst_data = data_json[0]['lst']
    elif isinstance(data_json, dict) and 'lst' in data_json:
        lst_data = data_json['lst']
    elif isinstance(data_json, list):
        lst_data = data_json
    else:
        return False, 0, "Định dạng JSON không hợp lệ (không tìm thấy data array)"
        
    # Convert JSON to XML
    xml_str = json_to_xml(lst_data)
    logger.info(f"XML Converted for {config.key}: {len(xml_str)} bytes")
    
    # DB Mapping
    count = 0
    if config.key == 'API_DANH_MUC_DON_VI_QUAN_LY':
        for item in lst_data:
            code = item.get('MA_DONVI')
            if code:
                ManagementUnit.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN_DONVI', ''),
                        'sort_order': str(item.get('SAPXEP', '')),
                        'parent_code': item.get('MA_DONVI_CHA', ''),
                        'unit_level': item.get('CAP_DONVI', 1)
                    }
                )
                count += 1
    elif config.key == 'API_TRAM':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_TRAM')
            if code:
                Station.objects.update_or_create(
                    station_code=code,
                    defaults={
                        'station_name': item.get('TEN') or item.get('TEN_TRAM', ''),
                        'id_tba': item.get('ID_TBA', ''),
                        'id_tinh': item.get('ID_TINH', ''),
                        'tinh': item.get('TINH', ''),
                        'id_quan': item.get('ID_QUAN', ''),
                        'quan': item.get('QUAN', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'id_dvi': item.get('ID_DVI', ''),
                        'id_sohuu': item.get('ID_SOHUU', '')
                    }
                )
                count += 1
    elif config.key == 'API_NGAN_LO':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_NLO')
            if code:
                Bay.objects.update_or_create(
                    bay_code=code,
                    defaults={
                        'bay_name': item.get('TEN') or item.get('TEN_NLO', ''),
                        'ten_tram': item.get('TEN_TRAM', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'id_dvi': item.get('ID_DVI', ''),
                        'id_nlo': item.get('ID_NLO', ''),
                        'id_tba': item.get('ID_TBA', ''),
                        'id_sohuu': item.get('ID_SOHUU', ''),
                        'u_dm': item.get('U_DM', ''),
                        'i_dm': item.get('I_DM', ''),
                        'sdm': item.get('SDM', '')
                    }
                )
                count += 1
    elif config.key == 'API_THIET_BI':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_TBI')
            if code:
                Relay.objects.update_or_create(
                    relay_code=code,
                    defaults={
                        'relay_name': item.get('TEN') or item.get('TEN_TBI', ''),
                        'manufacturer': item.get('TEN_HANG_SX', ''),
                        'id_tbi': item.get('ID_TBI', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'id_hang_sx': item.get('ID_HANG_SX', ''),
                        'id_nuoc_sx': item.get('ID_NUOC_SX', ''),
                        'id_loai_tb': item.get('ID_LOAI_TB', ''),
                        'id_loai_dt': item.get('ID_LOAI_DT', ''),
                        'id_doituong': item.get('ID_DOITUONG', ''),
                        'id_dvi': item.get('ID_DVI', ''),
                        'id_sohuu': item.get('ID_SOHUU', ''),
                        'id_vtri_dat': item.get('ID_VTRI_DAT', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_NUOC_SAN_XUAT':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_NUOC')
            if code:
                ManufacturingCountry.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_NUOC', ''),
                        'legacy_id': item.get('ID_NUOC_SX', ''),
                        'sort_order': str(item.get('SAPXEP', ''))
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_HANG_SAN_XUAT':
        for item in lst_data:
            code = item.get('ID') or item.get('MA') or item.get('MA_HANG')
            if code:
                Manufacturer.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_HANG', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_SO_HUU':
        for item in lst_data:
            code = item.get('ID') or item.get('MA') or item.get('MA_SOHUU')
            if code:
                Ownership.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_SOHUU', ''),
                        'sort_order': str(item.get('SAPXEP', ''))
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_CAP_DIEN_AP':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_CAPDA')
            if code:
                VoltageLevel.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_CAPDA', ''),
                        'legacy_code': item.get('MA_PHU', ''),
                        'sort_order': str(item.get('SAPXEP', ''))
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_LOAI_THIET_BI':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_LOAI_TB')
            if code:
                EquipmentType.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_LOAI_TB', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_TRANG_THAI':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_TTVH')
            if code:
                OperationalStatus.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_TTVH', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_DUONG_DAY':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_DZ')
            if code:
                Line.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_DZ', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'da_tke': item.get('DA_TKE', ''),
                        'id_da_tke': item.get('ID_DA_TKE', ''),
                        'i_chophep': item.get('I_CHOPHEP', ''),
                        'tong_cdai': item.get('TONG_CDAI', ''),
                        'so_mach': item.get('SO_MACH', ''),
                        'id_dvi': item.get('ID_DVI', ''),
                        'id_sohuu': item.get('ID_SOHUU', ''),
                        'id_dz': item.get('ID_DZ', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_CONG_TRINH':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_CT')
            if code:
                Project.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_CT', ''),
                        'id_ct': item.get('ID_CT', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'nam_xd': item.get('NAM_XD', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'ma_ct_cha': item.get('MA_CT_CHA', ''),
                        'ten_ct_cha': item.get('TEN_CT_CHA', ''),
                        'id_sohuu': item.get('ID_SOHUU', ''),
                        'id_dvi': item.get('ID_DVI', '')
                    }
                )
                count += 1
    elif config.key == 'API_DANH_MUC_VI_TRI':
        for item in lst_data:
            code = item.get('MA') or item.get('MA_VITRI')
            if code:
                Location.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': item.get('TEN', '') or item.get('TEN_VITRI', ''),
                        'id_vitri': item.get('ID_VITRI', ''),
                        'id_capda': item.get('ID_CAPDA', ''),
                        'id_ttvh': item.get('ID_TTVH', ''),
                        'khoang_neo': item.get('KHOANG_NEO', ''),
                        'khoang_cot': item.get('KHOANG_COT', ''),
                        'id_khuvuc': item.get('ID_KHUVUC', ''),
                        'khu_vuc': item.get('KHU_VUC', ''),
                        'id_dvi': item.get('ID_DVI', ''),
                        'id_sohuu': item.get('ID_SOHUU', ''),
                        'id_ct': item.get('ID_CT', ''),
                        'ten_ct': item.get('TEN_CT', '')
                    }
                )
                count += 1
    else:
        # Default generic mapping handler
        count = len(lst_data)
        
    # Tự động liên kết khóa ngoại sau khi đồng bộ
    if config.key in ['API_TRAM', 'API_NGAN_LO', 'API_THIET_BI']:
        try:
            run_linking()
            logger.info("Automatically linked Bays and Relays foreign keys.")
        except Exception as e:
            logger.error(f"Failed to link data: {e}")
        
    return True, count, ""
