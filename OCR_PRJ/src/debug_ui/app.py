"""Readable Streamlit UI for debugging PDF splitting and OCR extraction."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

import streamlit as st

from src.debug_ui.pipeline import PdfCandidate, PdfOcrDebugPipeline


OUTPUT_ROOT = Path("output") / "debug_ui" / "sessions"
FIELD_LABELS = {
    "ticket_number": "Số phiếu",
    "page_reference": "Trang",
    "station": "Trạm",
    "protected_equipment": "Thiết bị được bảo vệ",
    "protection_type": "Kiểu bảo vệ",
    "circuit_breaker": "Máy cắt",
    "relay_name": "Tên rơ-le",
    "relay_version": "Phiên bản rơ-le",
    "relay_serial": "Số hiệu rơ-le",
    "current_transformer_ratio": "Tỷ số biến dòng điện",
    "voltage_transformer_ratio": "Tỷ số biến điện áp",
    "manufacturer": "Nhà chế tạo / sản xuất",
    "installation_year": "Năm lắp đặt",
    "software": "Phần mềm",
    "software_version": "Phiên bản phần mềm",
    "protection_cabinet": "Tủ bảo vệ",
    "protection_circuit": "Mạch bảo vệ",
    "issuance_purpose": "Mục đích ban hành phiếu",
    "dispatch_center_request": "Yêu cầu của Trung tâm Điều độ",
}


def _initialise_state() -> None:
    defaults = {
        "debug_session_id": uuid.uuid4().hex[:12],
        "pdf_candidates": [],
        "ocr_results": {},
        "split_manifest": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _workspace() -> Path:
    return (OUTPUT_ROOT / st.session_state.debug_session_id).resolve()


@st.cache_resource(show_spinner=False)
def _pipeline(use_gpu: bool, render_dpi: int) -> PdfOcrDebugPipeline:
    return PdfOcrDebugPipeline(use_gpu=use_gpu, render_dpi=render_dpi)


def _candidate_objects() -> list[PdfCandidate]:
    return [PdfCandidate(**item) for item in st.session_state.pdf_candidates]


def _save_candidates(candidates: list[PdfCandidate]) -> None:
    st.session_state.pdf_candidates = [candidate.as_dict() for candidate in candidates]
    st.session_state.ocr_results = {}


def _progress_callback(bar, label):
    def update(current: int, total: int, message: str) -> None:
        bar.progress(min(1.0, current / max(total, 1)))
        label.caption(message)
    return update


def _render_candidate_table(candidates: list[PdfCandidate]) -> None:
    st.dataframe(
        [
            {
                "PDF_x": candidate.name,
                "Số trang": candidate.page_count,
                "Nguồn": "Tách từ PDF_A" if candidate.origin == "split_from_pdf_a" else "PDF phiếu có sẵn",
                "Đường dẫn debug": candidate.path,
            }
            for candidate in candidates
        ],
        use_container_width=True,
        hide_index=True,
    )


def _field_rows(result: dict) -> list[dict]:
    fields = result.get("important_fields", {})
    source_labels = result.get("important_source_labels", {})
    preferred = [*FIELD_LABELS, *(name for name in fields if name not in FIELD_LABELS)]
    return [
        {
            "Trường dữ liệu": FIELD_LABELS.get(name, name),
            "Field key": name,
            "Nhãn gốc trên phiếu": source_labels.get(name),
            "Giá trị": fields.get(name),
            "Trạng thái": "Đã nhận diện" if fields.get(name) is not None else "null",
        }
        for name in preferred
    ]


def _raw_ocr_rows(page: dict) -> list[dict]:
    rows = []
    for region in page.get("raw_ocr", []):
        polygon = region.get("polygon") or []
        rows.append({
            "index": region.get("index"),
            "text": region.get("text"),
            "recognition_score": region.get("recognition_score"),
            "detection_score": region.get("detection_score"),
            "polygon": json.dumps(polygon, ensure_ascii=False),
        })
    return rows


def _render_result(candidate: PdfCandidate, result: dict) -> None:
    summary = result["summary"]
    st.subheader(candidate.name)
    metrics = st.columns(5)
    metrics[0].metric("Số trang", summary["pages"])
    metrics[1].metric("Trang đã OCR", summary["ocr_pages"])
    metrics[2].metric("Field có giá trị", summary["important_fields_populated"])
    metrics[3].metric("Setting records", summary["setting_records"])
    metrics[4].metric("Lưu ý", summary["note_candidates"])

    overview, settings, notes, pages, raw_json = st.tabs([
        "Thông tin quan trọng",
        "Thông số chỉnh định",
        "Lưu ý",
        "Debug theo trang",
        "JSON đầy đủ",
    ])
    with overview:
        st.dataframe(_field_rows(result), use_container_width=True, hide_index=True)
    with settings:
        records = result.get("setting_records", [])
        if records:
            st.dataframe(records, use_container_width=True, hide_index=True)
        else:
            st.info("Không có setting record nào được layout analysis tạo ra.")
    with notes:
        candidates = result.get("note_candidates", [])
        if not candidates:
            st.info("Chưa tìm thấy heading 'Lưu ý' trong raw OCR.")
        for note in candidates:
            st.markdown(f"**Trang {note['page_number']}**")
            st.text_area(
                "Raw OCR candidate",
                note["text"],
                height=180,
                key=f"note_{candidate.candidate_id}_{note['page_number']}",
            )
        st.caption("Phần Lưu ý hiện là raw OCR candidate để debug; chưa được coi là structured ground truth.")
    with pages:
        for page in result.get("pages", []):
            role = page["page_role"]
            title = f"Trang {page['page_number']} · {role} · {page['status']}"
            with st.expander(title, expanded=page["page_number"] == 1):
                left, right = st.columns([0.9, 1.1], gap="large")
                with left:
                    image_path = Path(page["image_path"])
                    if image_path.is_file():
                        st.image(str(image_path), caption=f"Trang {page['page_number']}", use_container_width=True)
                with right:
                    if page["status"].startswith("skipped"):
                        st.info("Page 2 được bỏ qua theo policy của phiếu; không chạy OCR/layout.")
                    else:
                        raw_rows = _raw_ocr_rows(page)
                        st.caption(f"{len(raw_rows)} OCR regions")
                        st.dataframe(raw_rows, use_container_width=True, hide_index=True, height=360)
                        layout = page.get("layout") or {}
                        warnings = layout.get("warnings") or ([layout["warning"]] if layout.get("warning") else [])
                        for warning in warnings:
                            st.warning(str(warning))
                        with st.expander("Layout JSON của trang"):
                            st.json(layout, expanded=False)
    with raw_json:
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        st.download_button(
            "Tải extraction.json",
            payload,
            file_name=f"{Path(candidate.name).stem}_extraction.json",
            mime="application/json",
            key=f"download_json_{candidate.candidate_id}",
        )
        st.json(result, expanded=False)


def main() -> None:
    st.set_page_config(page_title="PDF → OCR Debug Console", page_icon="🔎", layout="wide")
    _initialise_state()
    st.markdown("""
    <style>
      .stApp { background: #f4f7fb; }
      [data-testid="stHeader"] { background: rgba(244,247,251,.88); }
      .debug-hero { padding: 1.3rem 1.5rem; border-radius: 18px; color: white;
        background: linear-gradient(125deg,#102a43 0%,#176b87 58%,#64ccc5 100%);
        box-shadow: 0 14px 34px rgba(16,42,67,.16); margin-bottom: 1.2rem; }
      .debug-hero h1 { margin: 0; font-size: 2rem; }
      .debug-hero p { margin: .55rem 0 0; opacity: .88; }
      div[data-testid="stMetric"] { background: white; border: 1px solid #dbe5ef;
        border-radius: 14px; padding: .8rem 1rem; box-shadow: 0 5px 18px rgba(16,42,67,.05); }
      div[data-testid="stFileUploader"] { background: white; border: 1px dashed #9fb3c8;
        border-radius: 14px; padding: .65rem; }
      .step-label { color:#176b87; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
    </style>
    <div class="debug-hero">
      <h1>PDF → OCR Debug Console</h1>
      <p>Tách PDF_A, chọn PDF_x, chạy OCR và kiểm tra structured data cùng evidence.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.header("Cấu hình chạy")
        use_gpu = st.toggle("Dùng GPU", value=False, help="Chỉ bật khi Paddle/VietOCR GPU đã được cấu hình.")
        render_dpi = st.slider("Render DPI", 120, 240, 160, 20)
        st.caption(f"Session: `{st.session_state.debug_session_id}`")
        st.caption(f"Artifacts: `{_workspace()}`")
        if st.button("Xóa session debug", type="secondary", use_container_width=True):
            workspace = _workspace()
            expected_root = OUTPUT_ROOT.resolve()
            if workspace.is_relative_to(expected_root) and workspace.is_dir():
                shutil.rmtree(workspace)
            for key in ("debug_session_id", "pdf_candidates", "ocr_results", "split_manifest"):
                st.session_state.pop(key, None)
            st.rerun()

    pipeline = _pipeline(use_gpu, render_dpi)
    st.markdown('<div class="step-label">Bước 1 · Chuẩn bị PDF_x</div>', unsafe_allow_html=True)
    mode = st.radio(
        "Nguồn đầu vào",
        ["PDF_A lớn cần tách", "PDF_x có sẵn, không cần tách"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if mode == "PDF_A lớn cần tách":
        upload = st.file_uploader("Chọn một PDF_A", type=["pdf"], accept_multiple_files=False)
        if st.button("Tách PDF_A thành các PDF_x", type="primary", disabled=upload is None):
            try:
                source = pipeline.save_uploaded_pdf(upload.name, upload.getvalue(), _workspace() / "uploads" / "pdf_a")
                bar = st.progress(0.0)
                label = st.empty()
                candidates, manifest = pipeline.split_pdf_a(
                    source,
                    _workspace() / "splitter" / source.stem,
                    progress=_progress_callback(bar, label),
                )
                _save_candidates(candidates)
                st.session_state.split_manifest = manifest
                st.success(f"Đã tách thành {len(candidates)} PDF_x.")
            except Exception as exc:
                st.exception(exc)
    else:
        uploads = st.file_uploader(
            "Chọn một hoặc nhiều PDF_x",
            type=["pdf"],
            accept_multiple_files=True,
        )
        if st.button("Nạp các PDF_x", type="primary", disabled=not uploads):
            try:
                paths = [
                    pipeline.save_uploaded_pdf(upload.name, upload.getvalue(), _workspace() / "uploads" / "pdf_x")
                    for upload in uploads
                ]
                candidates = pipeline.candidates(paths, origin="direct_pdf_x")
                _save_candidates(candidates)
                st.session_state.split_manifest = None
                st.success(f"Đã nạp {len(candidates)} PDF_x; bước tách được bỏ qua.")
            except Exception as exc:
                st.exception(exc)

    candidates = _candidate_objects()
    st.divider()
    st.markdown('<div class="step-label">Bước 2 · Chọn PDF_x cần OCR</div>', unsafe_allow_html=True)
    if not candidates:
        st.info("Hãy tách PDF_A hoặc nạp các PDF_x có sẵn để tiếp tục.")
        return
    count_cols = st.columns([1, 4])
    count_cols[0].metric("Số PDF_x", len(candidates))
    with count_cols[1]:
        _render_candidate_table(candidates)
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    selected_ids = st.multiselect(
        "Chọn các PDF_x muốn trích xuất OCR",
        options=list(by_id),
        default=list(by_id),
        format_func=lambda candidate_id: f"{by_id[candidate_id].name} · {by_id[candidate_id].page_count} trang",
    )
    if st.button("Chạy OCR và layout analysis", type="primary", disabled=not selected_ids):
        bar = st.progress(0.0)
        label = st.empty()
        results = dict(st.session_state.ocr_results)
        for index, candidate_id in enumerate(selected_ids, start=1):
            candidate = by_id[candidate_id]
            label.caption(f"PDF_x {index}/{len(selected_ids)} · {candidate.name}")
            try:
                result = pipeline.extract_pdf_x(
                    candidate,
                    _workspace() / "extractions" / candidate.candidate_id,
                    progress=_progress_callback(bar, label),
                )
                results[candidate_id] = result
            except Exception as exc:
                st.error(f"Không thể xử lý {candidate.name}")
                st.exception(exc)
        st.session_state.ocr_results = results
        bar.progress(1.0)
        label.caption("Hoàn tất các PDF_x đã chọn")

    st.divider()
    st.markdown('<div class="step-label">Bước 3 · Kết quả và evidence</div>', unsafe_allow_html=True)
    available = [candidate_id for candidate_id in selected_ids if candidate_id in st.session_state.ocr_results]
    if not available:
        st.info("Chưa có kết quả. Chọn PDF_x và bấm chạy OCR.")
        return
    inspected_id = st.selectbox(
        "PDF_x đang xem",
        options=available,
        format_func=lambda candidate_id: by_id[candidate_id].name,
    )
    _render_result(by_id[inspected_id], st.session_state.ocr_results[inspected_id])


if __name__ == "__main__":
    main()
