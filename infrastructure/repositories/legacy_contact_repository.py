"""Repository adapter around the existing Contact class."""

from __future__ import annotations

from domain.types import RawContact
from ports.contact_repository_port import ContactRepositoryPort
from Classes.Contact import Contact


class LegacyContactRepository(ContactRepositoryPort):
    """Wrap the current contact retrieval logic so it can be used as a port adapter."""

    def __init__(self, test: bool = True, filter_columns: list | None = None) -> None:
        self.test = test
        self.filter_columns = filter_columns or []
        self.contact = Contact(test=test, filter_columns=self.filter_columns)

    def get_contacts(self) -> list[RawContact]:
        return self.contact.get_all_contacts()
