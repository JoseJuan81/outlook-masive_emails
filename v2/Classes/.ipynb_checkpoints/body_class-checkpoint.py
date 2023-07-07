"""Módulo para construir Cuerpo de correo usando la clase HtmlBody"""

from pathlib import Path
from Classes.base64_converter import Base64Converter

class HtmlBody:
    """Construir plantilla del cuerpo del correo"""

    body_imgs_path = Path("./html/images/body")
    body_html_path = Path("./html/templates/body_html.html")

    def __init__(self) -> None:
        self.images = []
        self.body_str = ""
        self.get_images(self.body_imgs_path)
        self.build()

    def get_images(self, dir_path) -> None:
        """Obtiene las imágenes y convertirlas en base64"""
        for file in dir_path.iterdir():
            self.images.append(Base64Converter.convert_to_bs64(file))

    def body_fn(self, name):
        """Retorna plantilla con nombre de contacto"""
        self.body_str = self.body_html_path.read_text(encoding="utf-8")
        return self.body_str.format(name, [*self.images])

    def build(self) -> str:
        """Retorna la función que construye la plantilla body"""
        return self.body_fn
