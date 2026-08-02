"""Stable page-1 field names and Vietnamese label aliases."""

FIELD_SPECS = {
    "ticket_number": {"labels": ["Số phiếu", "Số phiếu chỉnh định"], "required": True, "source_policy": "header_right"},
    # Detect x/y plus header geometry; the label vocabulary is intentionally
    # open-ended (Trang, Page, Tờ, or previously unseen wording).
    "page_reference": {"labels": [], "required": True, "source_policy": "dynamic_header_pattern"},
    "station": {"labels": ["Trạm"], "required": True, "source_policy": "inline_or_right"},
    "protected_equipment": {"labels": ["Thiết bị được bảo vệ"], "source_policy": "right_cell"},
    "protection_type": {"labels": ["Kiểu bảo vệ"], "source_policy": "right_cell"},
    "circuit_breaker": {"labels": ["Máy cắt"], "source_policy": "right_cell"},
    "relay_name": {"labels": ["Tên rơ-le", "Tên role", "Tên rơ-je"], "source_policy": "right_cell"},
    "relay_version": {"labels": ["Phiên bản"], "source_policy": "right_cell", "allow_multiple": True},
    "wiring_diagram": {"labels": ["Sơ đồ đánh số"], "source_policy": "right_cell"},
    "relay_serial": {"labels": ["Số hiệu rơ-le", "Số hiệu role"], "source_policy": "right_cell"},
    "current_transformer_ratio": {
        "labels": ["Tỷ số biến dòng điện", "Tỷ số/ chỉ danh biến dòng điện", "Tỷ số chỉ danh biến dòng điện"],
        "source_policy": "right_cell",
    },
    "manufacturer": {"labels": ["Nhà chế tạo", "Nhà sản xuất"], "source_policy": "right_cell"},
    "voltage_transformer_ratio": {
        "labels": ["Tỷ số biến điện áp", "Tỷ số/ chỉ danh biến điện áp", "Tỷ số chỉ danh biến điện áp"],
        "source_policy": "right_cell",
    },
    "installation_year": {"labels": ["Năm lắp đặt"], "source_policy": "right_cell"},
    "single_line_drawing": {"labels": ["Số hiệu bản vẽ một sợi"], "source_policy": "right_cell"},
    "software": {"labels": ["Phần mềm"], "source_policy": "right_cell"},
    "protection_cabinet": {"labels": ["Tủ bảo vệ"], "source_policy": "right_cell"},
    "protection_circuit": {"labels": ["Mạch bảo vệ"], "source_policy": "right_cell"},
    "issuance_purpose": {"labels": ["Mục đích ban hành phiếu chỉnh định"], "required": True, "source_policy": "inline_or_right"},
    "dispatch_center_request": {"labels": ["Yêu cầu của Trung tâm Điều độ", "Yêu cầu của Trung tâm Điều độ:"], "required": True, "source_policy": "inline_or_right"},
}

PROTECTION_TABLE_ROLES = [
    "function", "protection_level", "setting_value", "delay_seconds",
    "external_control_signal", "action",
]

# These values are derived from anchored fields rather than detected by their
# own labels, but remain part of the stable JSON schema.
DERIVED_FIELD_NAMES = (
    "software_version",
    "page_number",
    "total_pages",
    "form_title",
    "protection_principle_heading",
)

PAGE1_FIELD_NAMES = (*FIELD_SPECS, *DERIVED_FIELD_NAMES)

# Canonical company form topology for the first (general-description) table.
# Canonical field ownership comes from row/side position; OCR labels are
# retained as evidence but are not used to decide these field names.
COVER_TABLE_ROWS = (
    (("protected_equipment", "left"), ("protection_type", "right")),
    (("circuit_breaker", "left"), ("relay_name", "right_primary"), ("relay_version", "right_secondary")),
    (("wiring_diagram", "left"), ("relay_serial", "right")),
    (("current_transformer_ratio", "left"), ("manufacturer", "right")),
    (("voltage_transformer_ratio", "left"), ("installation_year", "right")),
    (("single_line_drawing", "left"), ("software", "right_primary"), ("software_version", "right_secondary")),
    (("protection_cabinet", "left"), ("protection_circuit", "right")),
)

COVER_TABLE_FIELD_NAMES = tuple(
    field_name
    for row in COVER_TABLE_ROWS
    for field_name, _slot_name in row
)
