"""Módulo principal para ejecutar la aplicación: Envío masivo de correos"""

# from contacts import contacts
from outlook import outlook
from Classes.email_class import SendEmails
from helper.notion_helper import ContactColumns, Target

PLANTA = Target.PLANTA.value
MINA = Target.MINA.value
TUBERIA = Target.TUBERIA.value
COMPRAS =Target.COMPRAS.value

CONTACT_FILTERED = [
    (
        ContactColumns.AREA.value,
        [COMPRAS, PLANTA, MINA, TUBERIA]
    )
]

if __name__ == "__main__":
    emails = SendEmails()
    #emails.set_contacts(contacts)
    emails.get_contacts(test=True, filter_columns=CONTACT_FILTERED)
    emails.set_subject("Int-elle Corporation en Navidad 🎄🎄")
    emails.send(outlook)
    