"""Módulo para convertir imágenes en formato Base64"""

import base64
from pathlib import Path

class Base64Converter:
    """Clase para tratar archivos con base64"""

    @staticmethod
    def convert_to_bs64(file: str):
        """Function para convertir imagenes a base64"""
        # base64_img = ""
        with open(file, "rb") as img:
            img_b64 = base64.b64encode(img.read())
            img_b64 = img_b64.decode("utf-8")
            img_type = Path(file).suffix[1:]
            base64_img = f"data:image/{img_type};base64,{img_b64}"

        return base64_img
