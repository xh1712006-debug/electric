# Session Handoff

## Current Objective

- Goal: IMMEDIATE-010 — khóa phạm vi và bàn giao Local API v1.
- Current status: Hoàn thành; toàn bộ IMMEDIATE-001A–010 đã đóng.
- Branch / commit: `main`; code acceptance ở `8f4bebb`, evidence ở `b832edf`.

## Completed This Session

- [x] Xác nhận Local API/schema/CLI `1.0`, pipeline `0.7.0`.
- [x] Acceptance trước handoff đạt 10/10 executions trên 8 layout families.
- [x] Baseline `init.ps1` trước IMMEDIATE-010 đạt 249/249 tests.
- [x] Viết README, ARCHITECTURE và API.md cho source-checkout consumer.
- [x] Thêm release manifest, validator và báo cáo handoff tiếng Việt.

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Baseline | `powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1` | 249/249 pass | Trước mutation IMMEDIATE-010. |
| Handoff validator | `python -m scripts.local_api_v1_handoff --check-only` | Pass | Link/schema/fixture/version/docs. |
| Public smoke | `python -m unittest tests.test_local_api_handoff -v` | 8/8 pass | External Unicode cwd, CLI help và typed failure. |
| Combined contract | handoff + contract + models + consumer + acceptance | 64/64 pass | Không OCR lại corpus. |
| Acceptance audit | `acceptance_runner verify --full-artifact-audit` | 10/10 pass | Evidence IMMEDIATE-009 không đổi. |
| Full verification | `powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1` | 257/257 pass | Repository restartable. |
| Clean clone | local clone commit `fbade92` + `tests.test_local_api_handoff` | 8/8 pass | Clone vẫn clean sau public import/CLI/docs test. |

## Files Changed

- `README.md`, `API.md`, `ARCHITECTURE.md`.
- `docs/LOCAL_API_CONTRACT_V1.md`, `session-handoff.md`, `manual.md`.
- `contracts/local_api/v1/release_manifest.json`.
- `scripts/local_api_v1_handoff.py`, `tests/test_local_api_handoff.py`.
- `immediate.md`, `PROGRESS.md`, `feature_list.json` khi chốt evidence.

## Decisions Made

- V1 là synchronous one-PDF_x local Python API với JSON CLI adapter.
- Additive optional change được phép trong v1 nếu fixture/consumer cũ vẫn hợp lệ.
- Field/type/nullability/enum/error/artifact-boundary breaking change phải tăng major.
- Source checkout cần repository root trên `PYTHONPATH`; chưa tuyên bố có deployment package.
- Review-required candidate không được tự động ghi như approved data.

## Blockers / Risks

- Chưa có ground truth/quality threshold nên không công bố OCR accuracy.
- Chưa có installable package, dependency lock, offline bundle hoặc rollback runbook.
- Page 2 bị skip có warning; Page 1 Table 02 chưa extract; Page 3+ luôn review.
- Concurrency, resource limits, ACL và production UAT chưa được khóa.

## Next Session Startup

1. Read `AGENTS.md`.
2. Read `immediate.md`, `feature_list.json`, `PROGRESS.md` and this handoff.
3. Review this handoff.
4. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1` before editing.
5. Follow the mandatory task confirmation gate before repository mutation.

## Recommended Next Step

- PLAN-001 — Chốt phạm vi nghiệp vụ và ranh giới tích hợp.
- Sau PLAN-001, ưu tiên PLAN-002/003 cho ground truth/quality gates; packaging và
  deployment vẫn thuộc PLAN-009/018.
