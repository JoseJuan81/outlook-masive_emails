"""Genera y abre la vista previa del correo en el navegador."""

import argparse
from pathlib import Path

from infrastructure.services.html_email_builder import HtmlEmailBuilder
from infrastructure.services.html_preview_service import HtmlPreviewService

_PROJECT_ROOT = Path(__file__).resolve().parent
_BODY_FILE = _PROJECT_ROOT / "html/templates/body_html.html"


def _load_body() -> str:
    if _BODY_FILE.exists():
        return _BODY_FILE.read_text(encoding="utf-8")
    raise SystemExit(
        "No se encontró el cuerpo del correo. Ejecuta primero:\n  uv run import_email_template.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Vista previa del correo")
    parser.add_argument("--name", default="Nombre", help="Nombre del destinatario de prueba")
    args = parser.parse_args()

    builder = HtmlEmailBuilder(_load_body())
    html = builder.build(args.name)

    preview_service = HtmlPreviewService()
    path = preview_service.generate_preview(html, open_in_browser=True)
    print(f"Vista previa generada en: {path.resolve()}")


if __name__ == "__main__":
    main()
