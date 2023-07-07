"""Módulo para agrupar plantillas html y enviar correo a todos los contactos"""

from pathlib import Path
from Classes.sign_class import HtmlSign
from Classes.body_class import HtmlBody
from Classes.base_class import HtmlBase

path_to_body_template = Path("./html/templates/body_html.html")
path_to_base_template = Path("./html/templates/base_html.html")

class SendEmails:
    """Clase para construir y enviar plantilla con mensaje a cada contacto"""

    templates = {
        "base": object,
        "sign": None,
        "body": object,
    }

    def __init__(self):
        self.contacts = []
        self.email_subject = ""
        self.build_email()

    def build_email(self) -> None:
        """Construye la firma, cuerpo y base del correo"""
        self.build_email_sign()
        self.build_email_body()
        self.build_email_base()

    def set_contacts(self, contacts:list):
        """Establece los contacto a quienes se les enviará el correo"""
        self.contacts = contacts

    def set_subject(self, subject:str) -> None:
        """Establece el asunto del correo"""
        self.email_subject = subject

    def build_email_sign(self) -> None:
        """Construye la plantilla de la Firma del correo"""
        html_sign = HtmlSign()
        self.templates["sign"] = html_sign.build()

    def build_email_body(self):
        """Construye la plantilla del Cuerpo del correo"""
        html_body = HtmlBody()
        self.templates["body"] = html_body.build()

    def build_email_base(self) -> None:
        """Construye la plantilla base"""
        html_base = HtmlBase()
        self.templates["base"] = html_base.build()

    def send(self, outlook) -> None:
        """Enviar correo a cada contacto"""
        sign = self.templates["sign"]

        for name, email in self.contacts.values:
            first_name = name.split(" ")[0].title()
            body = self.templates["body"](first_name)

            mail = outlook.CreateItem(0)
            mail.Subject = self.email_subject
            mail.HTMLBody = self.templates["base"](body, sign)
            mail.To = email
            mail.Display()
            mail.Send()
            print("Correo enviado a: ", email)
            print("="*60)
