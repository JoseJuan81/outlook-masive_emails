"""Módulo para construir firma de correo usando la clase HtmlSign"""

from pathlib import Path
from Classes.base64_converter import Base64Converter

class HtmlSign:
    """Clase para construir plantilla: Firma de correo"""

    sign_imgs_path = Path("./html/images/sign")
    sign_html_path = Path("./html/templates/sign__html.html")
    intelle = "intelle"
    cccp = "cccp"
    achilles = "achilles"
    linkedin = "linkedin"

    def __init__(self) -> None:
        self.sign_str = None
        self.intelle_img = None
        self.cccp_img = None
        self.achilles_img = None
        self.linkedin_img = None

        self.get_images(self.sign_imgs_path)
        self.build()

    def get_images(self, dir_path) -> None:
        """Obtiene las imágenes y las convierte a base64"""

        for file in dir_path.iterdir():
            name = file.stem
            if name == self.linkedin:
                self.linkedin_img = Base64Converter.convert_to_bs64(file)

            if name == self.achilles:
                self.achilles_img = Base64Converter.convert_to_bs64(file)

            if name == self.intelle:
                self.intelle_img = Base64Converter.convert_to_bs64(file)

            if name == self.cccp:
                self.cccp_img = Base64Converter.convert_to_bs64(file)

    def build(self) -> str:
        """Construye la firma del correo con las imágenes"""
        self.sign_str = self.sign_html_path.read_text(encoding="utf-8")
        sign = self.sign_str.format(
            self.linkedin_img,
            self.intelle_img,
            self.cccp_img,
            self.achilles_img
        )
        return sign
