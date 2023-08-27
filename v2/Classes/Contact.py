import os
import requests

import pandas as pd

from pathlib import Path
from enum import Enum
from dotenv import load_dotenv
from helper.notion_helper import get_contact_prop_value, filter_by_contact_prop
from helper.notion_helper import ContactColumns

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_CONTACT_DB_ID = os.getenv("NOTION_CONTACT_DB_ID")


class Contact:

    def __init__(self, test=True, filter_columns=[]):
        self.test_mode = test
        self.all_contacts = []
        self.notion_url = f"https://api.notion.com/v1/databases/{NOTION_CONTACT_DB_ID}/query"
        self.notion_url_headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        }
        # self.files_init()
        if test:
            data = dict([
                (ContactColumns.NAME.value, [
                 "José Juan Domínguez López", "Noah David"]),
                (ContactColumns.EMAIL.value, [
                 "josejuan.dominguez@int-elle.com", "josejuan.dominguez@int-elle.com"]),
            ])
            test_data = pd.DataFrame(
                data=data,
                columns=[ContactColumns.NAME.value, ContactColumns.EMAIL.value]
            )
            self.all_contacts += test_data.to_dict(orient="records")
        else:
            self.notion_init(filter_columns)

    def files_init(self):
        """"""
        contacts_dir = Path("./../contactos/")
        all_contacts_files = contacts_dir.iterdir()

        all_contacts = set()

        # Recorro todos los archivos dentro de la carpeta contactos para obtener solo aquellos con extensión .csv
        for file in all_contacts_files:
            if file.is_file() and file.suffix == ".csv":
                content = pd.read_csv(file)
                all_contacts.append(content)

        self.all_contacts = pd.concat(all_contacts)
        self.all_contacts = self.unique_contacts(self.all_contacts)

    def unique_contacts(self):
        pass

    def notion_init(self, filter_columns):
        all_contact = self.get_contacts_from_notion()
        df_contacts = self.extract_contact_properties(all_contact)
        self.filter_by(df_contacts, filter_columns=filter_columns)

    def get_contacts_from_notion(self) -> list:
        """Función que se conecta a notion y obtiene todas las páginas de contactos"""
        print("Cargando contactos desde Notion...")
        all_contacts = []
        has_more = True
        next_cursor = None

        headers = self.notion_url_headers

        while has_more:

            try:

                data = {"start_cursor": next_cursor} if next_cursor else None
                print(data)
                res = requests.post(
                    self.notion_url, headers=headers, json=data)

                results_json = res.json()
            except:
                print(res.json())

            all_contacts += results_json["results"]
            has_more = results_json["has_more"]
            next_cursor = results_json["next_cursor"]

        print("="*50)
        print(f"Fueron encontrados {len(all_contacts)} contactos en Notion")
        print("="*50)
        return all_contacts

    def extract_contact_properties(self, contacts: list) -> pd.DataFrame:
        """Función que crea una lista de contactos nueva con las propiedades de mi interes"""

        # Crear una lista con las propiedades de cada página de contacto
        contacts_all_properties = [cts["properties"]
                                   for cts in contacts]
        new_contacts = []

        # Recorrer lista de propiedades y crear listado con las que me interesan nada mas
        for props in contacts_all_properties:
            name = get_contact_prop_value(ContactColumns.NAME, props)
            email = get_contact_prop_value(ContactColumns.EMAIL, props)
            area = get_contact_prop_value(ContactColumns.AREA, props)
            no_email = get_contact_prop_value(ContactColumns.NO_EMAIL, props)
            country = get_contact_prop_value(ContactColumns.COUNTRY, props)

            contact_data = dict([
                (ContactColumns.NAME.value, name),
                (ContactColumns.EMAIL.value, email),
                (ContactColumns.AREA.value, area),
                (ContactColumns.NO_EMAIL.value, no_email),
                (ContactColumns.COUNTRY.value, country),
            ])

            new_contacts.append(contact_data)

        print("="*50)
        print(
            f"{len(new_contacts)} Contactos transformados a DataFrame con propiedades de interés")
        print("="*50)
        return pd.DataFrame(new_contacts)

    def filter_by(self, contacts: pd.DataFrame, filter_columns: list()) -> None:
        """Función para filtrar DataFrame de contactos"""
        df = contacts

        # Filtrar registros: solo los que tengan correos electrónicos
        filter_email_is_not_none = (df[ContactColumns.EMAIL.value].notna())
        df_no_empty_email = df.loc[filter_email_is_not_none]

        # Filtrar registros: los que tengan desmarcado campo de No Correo Masivo
        filter_no_masive_email = (df[ContactColumns.NO_EMAIL.value] == False)
        _df = df_no_empty_email.loc[filter_no_masive_email]

        print("="*50)
        print(f"Resultados del primer filtrado: {len(_df)} contactos")
        print("="*50)

        # Filtrar por
        self.all_contacts = filter_by_contact_prop(
            filter_values=filter_columns, data_frame=_df)

        # COnvertir a una list de dict
        self.all_contacts = self.all_contacts.to_dict(orient="records")
        print("="*50)
        print(
            f"Resultado de aplicar filtros: {len(self.all_contacts)} contactos pasaron los filtros")
