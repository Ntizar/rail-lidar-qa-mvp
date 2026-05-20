from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DOCS = ROOT / "docs"
OUTPUT = ROOT / "output"


def main() -> None:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)

    for name in ["index.html", "app.js", "styles.css"]:
        shutil.copy2(WEB / name, DOCS / name)

    vendor_src = WEB / "vendor" / "three.module.js"
    vendor_dst = DOCS / "vendor"
    vendor_dst.mkdir(parents=True)
    if not vendor_src.exists():
        node_three = ROOT / "node_modules" / "three" / "build" / "three.module.js"
        if not node_three.exists():
            raise FileNotFoundError("No se encontro Three.js. Ejecuta npm install antes de construir la demo estatica.")
        vendor_src.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(node_three, vendor_src)
    shutil.copy2(vendor_src, vendor_dst / "three.module.js")

    analysis_src = OUTPUT / "last_analysis.json"
    if not analysis_src.exists():
        raise FileNotFoundError("No existe output/last_analysis.json. Ejecuta un analisis antes de construir docs/.")
    shutil.copy2(analysis_src, DOCS / "sample_analysis.json")

    report_src = OUTPUT / "informe_qa.html"
    if report_src.exists():
        shutil.copy2(report_src, DOCS / "informe_qa.html")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
