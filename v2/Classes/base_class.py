"""Módulo para construir Html base de correo usando la clase HtmlBase"""

from pathlib import Path

class HtmlBase:
    """Construir plantilla del cuerpo del correo"""

    base_html_path = Path("./html/templates/base_html.html")

    def __init__(self) -> None:
        self.build()

    def base_fn(self, body, sign):
        """Retorna plantilla con nombre de contacto"""
        base_str = self.base_html_path.read_text(encoding="utf-8")
        return base_str.format(body, sign)

    def build(self) -> str:
        """Retorna la función que construye la plantilla body"""
        return self.base_fn
