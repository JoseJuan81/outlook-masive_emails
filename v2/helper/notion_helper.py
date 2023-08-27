import pandas as pd

from enum import Enum


class ContactColumns(Enum):
    NAME = "Nombre"
    EMAIL = "Correo"
    AREA = "Area"
    NO_EMAIL = "NO Correo Masivo"
    COUNTRY = "País"


class Target(Enum):
    ALL = 'all'
    PLANTA = 'Planta'
    MINA = 'Mina'
    TUBERIA = 'Tuberia'
    COMPRAS = 'Compras'
    PERU = 'Perú'
    VENEZUELA = 'Venezuela'
    TEST = "José Juan Domínguez López"


def get_contact_name(props: dict) -> str:
    """Función para obtener el Nombre del contacto"""
    prop_name = ContactColumns.NAME.value

    name = props[prop_name]
    title,  = name["title"]
    plain_text = title["plain_text"]

    return plain_text


def get_contact_email(props: dict) -> str:
    """Función para obtener el correo del contacto"""
    prop_name = ContactColumns.EMAIL.value

    email = props[prop_name]

    return email["email"] if email else ""


def get_contact_area(props: dict) -> str:
    """Función para obtener el área al que pertenece el contacto"""
    prop_name = ContactColumns.AREA.value

    area = props[prop_name]
    selection = area["select"]

    return selection["name"] if selection else ""


def get_contact_no_email(props: dict) -> str:
    """Función para obtener el valor del campo No Correo Masivo del contacto"""
    prop_name = ContactColumns.NO_EMAIL.value

    no_email = props[prop_name]
    check = no_email["checkbox"]

    return check


def get_contact_country(props: dict) -> str:
    """Función para obtener el país al que pertenece el contacto"""
    prop_name = ContactColumns.COUNTRY.value

    country = props[prop_name]
    selection = country["select"]

    return selection["name"] if selection else ""


def get_contact_prop_value(prop_name: str, props: dict) -> str | int | bool:
    """Función para obtener los valores de las propiedades del contacto"""
    prop_options = dict([
        (ContactColumns.NAME, lambda: get_contact_name(props)),
        (ContactColumns.EMAIL, lambda: get_contact_email(props)),
        (ContactColumns.AREA, lambda: get_contact_area(props)),
        (ContactColumns.NO_EMAIL, lambda: get_contact_no_email(props)),
        (ContactColumns.COUNTRY, lambda: get_contact_country(props))
    ])

    prop_value = prop_options[prop_name]
    return prop_value()


def filter_by_contact_prop(filter_values: list(), data_frame: pd.DataFrame) -> pd.DataFrame:
    """Función que filtra dataframes por propiedades del contacto"""
    try:
        if not isinstance(filter_values, list) or len(filter_values) == 0:
            return data_frame

        # DataFrame clonado de data_frame
        df = pd.DataFrame(
            data=data_frame.values, columns=data_frame.columns)

        # Recorrer uno a uno los filtros
        for fil in filter_values:
            column, fval_arr = fil

            # Recorro uno a uno el valor del filtro por columna
            helper_arr = pd.DataFrame(columns=data_frame.columns)
            for fv in fval_arr:
                print(f"Filtro: {column} ---> {fv}")
                filtering = (df[column] == fv)
                filtered_data = df.loc[filtering]
                # print("**"*60)
                # print(df.head(10))
                # print("**"*60)

                helper_arr = pd.DataFrame(
                    data=pd.concat([filtered_data, helper_arr]),
                    columns=data_frame.columns
                )
                # print("**"*50)
                # print(helper_arr.head(10))
                # print("**"*50)

            df = pd.DataFrame(
                data=helper_arr.values, columns=helper_arr.columns)

        # print("%%%"*50)
        # print(df.head(50))
        # print("%%%"*50)
        return df

    except ValueError:
        print("error del tipo ValueError filtrando Data frame desde función filter_by_contact_prop")
        return data_frame
    except TypeError:
        print("error del tipo TypeError filtrando Data frame desde función filter_by_contact_prop")
        return data_frame
