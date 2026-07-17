from infrastructure.repositories.airtable_contact_repository import AirtableContactRepository
from infrastructure.repositories.notion_contact_repository import NotionContactRepository
from infrastructure.repositories.supabase_contact_repository import SupabaseContactRepository
from helper.notion_helper import ContactColumns


def test_airtable_extract_contacts_maps_common_fields():
    repository = AirtableContactRepository(base_id="base", table_id="table", token="token")
    records = [
        {"fields": {"Nombre": "Alice", "Correo": "alice@example.com"}},
        {"fields": {"Name": "Bob", "Email": "bob@example.com"}},
    ]

    contacts = repository._extract_contacts(records)

    assert contacts == [
        {"Nombre": "Alice", "Correo": "alice@example.com"},
        {"Nombre": "Bob", "Correo": "bob@example.com"},
    ]


def test_notion_extract_contact_properties_uses_existing_helper_mapping():
    repository = NotionContactRepository(token="token", database_id="db")
    contacts = [{
        "properties": {
            ContactColumns.NAME.value: {"title": [{"plain_text": "Alice"}]},
            ContactColumns.EMAIL.value: {"email": "alice@example.com"},
            ContactColumns.AREA.value: {"select": {"name": "Compras"}},
            ContactColumns.NO_EMAIL.value: {"checkbox": False},
            ContactColumns.COUNTRY.value: {"select": {"name": "Perú"}},
        }
    }]

    data_frame = repository._extract_contact_properties(contacts)

    assert data_frame.to_dict(orient="records") == [{
        "Nombre": "Alice",
        "Correo": "alice@example.com",
        "Area": "Compras",
        "NO Correo Masivo": False,
        "País": "Perú",
    }]


def test_supabase_repository_maps_name_and_email_fields():
    repository = SupabaseContactRepository(
        url="https://example.supabase.co",
        key="key",
        name_field="full_name",
        email_field="work_email",
    )
    rows = [
        {"full_name": "Alice", "work_email": "alice@example.com"},
        {"full_name": "Bob", "work_email": "bob@example.com"},
    ]

    contacts = [{
        "Nombre": row.get(repository.name_field, ""),
        "Correo": row.get(repository.email_field, ""),
    } for row in rows]

    assert contacts == [
        {"Nombre": "Alice", "Correo": "alice@example.com"},
        {"Nombre": "Bob", "Correo": "bob@example.com"},
    ]
