import openpyxl
import random

# Tạo workbook và sheet
wb = openpyxl.Workbook()
sheet = wb.active
sheet.title = "MasterData"

# Dòng Header
sheet.append(["Mã Trạm", "Tên Trạm", "Mã Ngăn lộ", "Tên Ngăn lộ", "Mã Rơ-le", "Tên Rơ-le", "Hãng SX"])

# Cấu hình Trạm và Ngăn lộ
stations_config = [
    {
        "code": "TBA_500_HN",
        "name": "Trạm 500kV Hà Nội",
        "bays": [
            {"code": "BAY_500_1", "name": "Ngăn 500kV Số 1", "relay_count": 100},
            {"code": "BAY_500_2", "name": "Ngăn 500kV Số 2", "relay_count": 150},
            {"code": "BAY_500_3", "name": "Ngăn 500kV Số 3", "relay_count": 120},
        ]
    },
    {
        "code": "TBA_220_HP",
        "name": "Trạm 220kV Hải Phòng",
        "bays": [
            {"code": "BAY_220_A", "name": "Ngăn 220kV Lộ A", "relay_count": 100},
            {"code": "BAY_220_B", "name": "Ngăn 220kV Lộ B", "relay_count": 130},
            {"code": "BAY_220_C", "name": "Ngăn 220kV Lộ C", "relay_count": 140},
            {"code": "BAY_220_D", "name": "Ngăn 220kV Lộ D", "relay_count": 110},
        ]
    }
]

manufacturers = ["Siemens", "ABB", "GE", "SEL", "Schneider", "Toshiba"]
relay_types = ["Rơ-le So lệch", "Rơ-le Khoảng cách", "Rơ-le Quá dòng", "Rơ-le Chạm đất", "Rơ-le Kém áp", "Rơ-le Đảo pha"]

# Tạo dữ liệu
for station in stations_config:
    for bay in station["bays"]:
        for i in range(1, bay["relay_count"] + 1):
            r_code = f"REL_{bay['code'].split('_')[-1]}_{i:03d}"
            r_type = random.choice(relay_types)
            r_manuf = random.choice(manufacturers)
            
            row = [
                station["code"],
                station["name"],
                bay["code"],
                bay["name"],
                r_code,
                f"{r_type} Số {i}",
                r_manuf
            ]
            sheet.append(row)

# Lưu file
file_path = "d:/project/dien-luc/Data_Test_SLL.xlsx"
wb.save(file_path)
print(f"File created at {file_path}")
