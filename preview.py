"""Genera y abre la vista previa del correo en el navegador."""

import argparse

from infrastructure.services.html_email_builder import HtmlEmailBuilder
from infrastructure.services.html_preview_service import HtmlPreviewService


def main() -> None:
    parser = argparse.ArgumentParser(description="Vista previa del correo")
    parser.add_argument("--name", default="Nombre", help="Nombre del destinatario de prueba")
    args = parser.parse_args()

    builder = HtmlEmailBuilder()
    builder.build_email()
    html = builder.build(args.name)

    preview_service = HtmlPreviewService()
    path = preview_service.generate_preview(html, open_in_browser=True)
    print(f"Vista previa generada en: {path.resolve()}")


if __name__ == "__main__":
    main()
