from helper.notion_helper import get_contact_prop_value, ContactColumns, Target
from Classes.Contact import Contact
from helper.test_data import CONTACT_PROPERTIES_DATA


class TestContact:
    @classmethod
    def setup_class(cls):
        """Función que se ejecuta 1 vez antes de las pruebas"""
        cls.contacts = Contact()
        cls.contacts_data = cls.contacts.get_contacts_from_notion()

    def test_get_connected(self):
        """Prueba para verificar conexión con BD de Contactos en Notion"""
        assert len(self.contacts_data) > 300

    def test_check_contact_properties(self):
        expect = "Correo"
        contact_1, *_ = self.contacts_data
        any_contact_properties = contact_1["properties"].keys()
        assert expect in any_contact_properties

    def test_get_contact_prop_value_name(self):
        name = get_contact_prop_value(
            ContactColumns.NAME, CONTACT_PROPERTIES_DATA)
        expected = "Carlos Rabanal"
        assert name == expected

    def test_get_contact_prop_value_email(self):
        name = get_contact_prop_value(
            ContactColumns.EMAIL, CONTACT_PROPERTIES_DATA)
        expected = "Crabanal17@gmail.com"
        assert name == expected

    def test_get_contact_prop_value_area(self):
        name = get_contact_prop_value(
            ContactColumns.AREA, CONTACT_PROPERTIES_DATA)
        expected = "Planta"
        assert name == expected

    def test_get_contact_prop_value_no_email(self):
        name = get_contact_prop_value(
            ContactColumns.NO_EMAIL, CONTACT_PROPERTIES_DATA)
        expected = False
        assert name == expected

    def test_extract_contact_properties(self):
        """Prueba para verificar las propiedades del contacto"""
        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)
        contact_properties, *_ = df_contacts.to_dict(
            orient="records")

        assert ContactColumns.NAME.value in contact_properties
        assert ContactColumns.EMAIL.value in contact_properties
        assert ContactColumns.AREA.value in contact_properties
        assert ContactColumns.NO_EMAIL.value in contact_properties
        assert ContactColumns.COUNTRY.value in contact_properties

    def test_filter_by_email(self):
        """Prueba de filtrado de contactos: Solo los que tienen correos"""
        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)
        self.contacts.filter_by(df_contacts, filter_columns=[])
        serie = self.contacts.all_contacts
        assert all([c[ContactColumns.EMAIL.value] != "" for c in serie])
        assert all([c[ContactColumns.EMAIL.value] != None for c in serie])

    def test_filter_by_no_masive_email(self):
        """Prueba de filtrado de contactos: Solo los que tienen correos"""
        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)
        self.contacts.filter_by(df_contacts, filter_columns=[])
        serie = self.contacts.all_contacts
        assert all([s[ContactColumns.NO_EMAIL.value] is False for s in serie])

    def test_filter_by_area(self):
        """Prueba de filtrado de contactos: Solo los que tienen Area = Planta"""

        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)

        filter_value = [(
            ContactColumns.AREA.value,
            [Target.COMPRAS.value]
        )]

        self.contacts.filter_by(
            contacts=df_contacts,
            filter_columns=filter_value
        )

        serie = self.contacts.all_contacts

        assert len(serie) > 0
        assert all([
            s[ContactColumns.AREA.value] == Target.COMPRAS.value for s in serie
        ])

    def test_by_country(self):
        """Prueba de filtrado de contactos: Solo los que tienen País = Peru"""

        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)

        filter_value = [(
            ContactColumns.COUNTRY.value,
            [Target.PERU.value]
        )]

        self.contacts.filter_by(
            contacts=df_contacts,
            filter_columns=filter_value
        )

        serie = self.contacts.all_contacts

        assert len(serie) > 0
        assert all([
            s[ContactColumns.COUNTRY.value] == Target.PERU.value for s in serie
        ])

    def test_filter_by_country_and_area(self):
        """Prueba de filtrado de contactos: Solo los que tienen País = Peru"""

        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)

        filts = [
            (ContactColumns.COUNTRY.value, [Target.PERU.value]),
            (ContactColumns.AREA.value, [Target.PLANTA.value])
        ]

        self.contacts.filter_by(contacts=df_contacts, filter_columns=filts)
        serie = self.contacts.all_contacts

        assert len(serie) > 0
        assert all([
            a[ContactColumns.COUNTRY.value] == Target.PERU.value for a in serie])
        assert all([
            a[ContactColumns.AREA.value] == Target.PLANTA.value for a in serie])

    def test_filter_by_many_areas_and_many_countries(self):
        """Prueba de filtrado de contactos: Paises = Perú y Venezuela, Areas = Planta, Mina y Compras"""
        df_contacts = self.contacts.extract_contact_properties(
            self.contacts_data)

        filts = [
            (
                ContactColumns.COUNTRY.value,
                [Target.VENEZUELA.value, Target.PERU.value]
            ),
            (
                ContactColumns.AREA.value,
                [Target.MINA.value, Target.COMPRAS.value, Target.PLANTA.value]
            )
        ]

        self.contacts.filter_by(contacts=df_contacts, filter_columns=filts)
        serie = self.contacts.all_contacts

        assert len(serie) > 0

        # Verificar Paises
        countries = [s[ContactColumns.COUNTRY.value] for s in serie]
        assert Target.PERU.value in countries
        assert Target.VENEZUELA.value in countries

        # Verificar áreas
        areas = [s[ContactColumns.AREA.value] for s in serie]
        assert Target.MINA.value in areas
        assert Target.PLANTA.value in areas
        assert Target.COMPRAS.value in areas
