"""Vietnamese visual review for workspace isolation and artifact integrity."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
from typing import Mapping

from .workspace import load_workspace_manifest


def render_workspace_review(manifest: Mapping[str, object], output_path: Path | str) -> Path:
    output = Path(output_path)
    source = manifest.get("source") if isinstance(manifest.get("source"), Mapping) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    artifact_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('artifact_id', '—')))}</td>"
        f"<td>{escape(str(item.get('kind', '—')))}</td>"
        f"<td><code>{escape(str(item.get('relative_path', '—')))}</code></td>"
        f"<td>{escape(str(item.get('size_bytes', '—')))}</td>"
        f"<td><code>{escape(str(item.get('sha256', ''))[:12])}…</code></td>"
        "</tr>"
        for item in artifacts
        if isinstance(item, Mapping)
    ) or '<tr><td colspan="5">Chưa có artifact nghiệp vụ.</td></tr>'
    unchanged = source.get("unchanged") is True
    workspace_id = escape(str(manifest.get("workspace_id", "Chưa xác định")))
    html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kiểm thử trực quan workspace và artifact isolation</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:#172033;font-family:Segoe UI,Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}}h1{{margin:0 0 6px}}h2{{margin-top:30px}}.subtitle{{color:#52627a}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:13px}}.card,.panel{{background:white;border:1px solid #dbe4ef;border-radius:13px;padding:17px;box-shadow:0 2px 9px #1720330d}}
.card small{{display:block;color:#607087}}.card strong{{display:block;margin-top:6px;font-size:19px}}.ok{{color:#087f5b}}.bad{{color:#c92a2a}}
.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.step{{background:#eaf2ff;border-left:4px solid #2878d0;border-radius:10px;padding:14px}}
table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #e6edf6}}th{{background:#eaf0f8}}code{{background:#edf2f7;padding:2px 5px;border-radius:4px}}
.guard{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}@media(max-width:760px){{.flow,.guard{{grid-template-columns:1fr}}table{{font-size:13px}}}}
</style></head><body><main>
<h1>Kiểm thử trực quan workspace và artifact isolation</h1>
<p class="subtitle">IMMEDIATE-006 — workspace riêng cho từng call, source bất biến và mọi artifact có checksum.</p>
<section class="grid">
 <div class="card"><small>Workspace ID</small><strong>{workspace_id}</strong></div>
 <div class="card"><small>Trạng thái</small><strong>{escape(str(manifest.get('status', '—')))}</strong></div>
 <div class="card"><small>Artifact đã kiểm kê</small><strong>{len(artifacts)}</strong></div>
 <div class="card"><small>Source PDF</small><strong class="{'ok' if unchanged else 'bad'}">{'Không thay đổi' if unchanged else 'Đã thay đổi / chưa xác nhận'}</strong></div>
</section>
<h2>Vòng đời workspace</h2><section class="flow">
 <div class="step"><strong>1. Reserve</strong><br>Tạo độc quyền <code>output_root/correlation_id</code>.</div>
 <div class="step"><strong>2. Process</strong><br>Chỉ ghi trong workspace có marker hợp lệ.</div>
 <div class="step"><strong>3. Verify</strong><br>Kiểm tra path, size, SHA-256 và source hash.</div>
 <div class="step"><strong>4. Finalize</strong><br>Ghi manifest nguyên tử; cleanup luôn dry-run trước.</div>
</section>
<h2>Danh sách artifact trong manifest</h2><table><thead><tr><th>ID</th><th>Loại</th><th>Đường dẫn tương đối</th><th>Bytes</th><th>SHA-256</th></tr></thead><tbody>{artifact_rows}</tbody></table>
<h2>Hàng rào an toàn</h2><section class="guard">
 <div class="panel"><strong>Được phép</strong><p>File thường nằm dưới workspace, relative path dùng dấu <code>/</code>, correlation ID hợp lệ và checksum ổn định.</p></div>
 <div class="panel"><strong>Bị từ chối</strong><p>Workspace tồn tại, <code>..</code>, absolute path, symlink, Windows reparse point, marker giả và cleanup chưa xác nhận.</p></div>
</section>
<h2>Hash source trước và sau</h2><div class="panel"><code>{escape(str(source.get('sha256_before', '—')))}</code><br><code>{escape(str(source.get('sha256_after', '—')))}</code></div>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinh báo cáo tiếng Việt cho workspace OCR.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/workspace_isolation/workspace_review.html"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = load_workspace_manifest(args.manifest)
    output = render_workspace_review(manifest, args.output)
    print(f"Report: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_workspace_review"]
