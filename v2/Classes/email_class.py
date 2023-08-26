"""Módulo para agrupar plantillas html y enviar correo a todos los contactos"""

from pathlib import Path
from Classes.sign_class import HtmlSign
from Classes.body_class import HtmlBody
from Classes.base_class import HtmlBase
from Classes.Contact import Contact
from helper.notion_helper import ContactColumns

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
        self.contact = None
        self.contacts = []
        self.email_subject = ""
        self.contacts_len = 0
        self.build_email()

    def build_email(self) -> None:
        """Construye la firma, cuerpo y base del correo"""
        self.build_email_sign()
        self.build_email_body()
        self.build_email_base()

    def get_contacts(self, test=True, filter_columns=[]) -> None:
        self.contact = Contact(test=test, filter_columns=filter_columns)
        self.contacts = self.contact.all_contacts
        self.contacts_len = len(self.contacts)

    def set_contacts(self, contacts: list):
        """Establece los contacto a quienes se les enviará el correo"""
        self.contacts = contacts
        self.contacts_len = len(contacts)

    def set_subject(self, subject: str) -> None:
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
        counter = 1

        print("="*60)
        print("Estas en modo: PRUEBA") if self.contact.test_mode else print(
            "Estas en modo PRODUCCIÓN")

        print(f"Enviarás el correo a: {self.contacts_len} contacto(s)")

        user_confirmation = input(
            "Estas seguro de continuar?:\nS - Si\nN - No\n")

        if user_confirmation.lower() in ["s", "si", "sí"]:
            # Lista formada por dict
            for contact in self.contacts[36:]:
                print(contact)
                name, email, *_ = contact.values()

                first_name = name.split(" ")[0].title()
                body = self.templates["body"](first_name)

                mail = outlook.CreateItem(0)
                mail.Subject = self.email_subject
                mail.HTMLBody = self.templates["base"](body, sign)
                mail.To = email
                mail.Display()
                mail.Send()
                print(
                    f"Correo {counter} / {self.contacts_len} enviado")
                print("="*60)
                counter += 1
        else:
            print("="*60)
            print("Programa cancelado por el usuario")

        print("FIN")
