"""Repository that merges multiple contact sources and removes duplicate emails."""

from __future__ import annotations

from domain.entities import ContactEntity
from domain.types import RawContact
from ports.contact_repository_port import ContactRepositoryPort


class MultiContactRepository(ContactRepositoryPort):
    """Combine repositories while preserving order of first appearance."""

    def __init__(self, repositories: list[ContactRepositoryPort]) -> None:
        self.repositories = repositories

    def get_contacts(self) -> list[RawContact] | list[ContactEntity]:
        merged_contacts: list[RawContact] | list[ContactEntity] = []
        seen_emails = set()

        for repository in self.repositories:
            for contact in repository.get_contacts():
                email = self._get_email(contact)
                email_key = (email or "").strip().lower()

                if email_key and email_key in seen_emails:
                    continue

                if email_key:
                    seen_emails.add(email_key)

                merged_contacts.append(contact)

        return merged_contacts

    def _get_email(self, contact: RawContact | ContactEntity) -> str:
        if isinstance(contact, dict):
            values = list(contact.values())
            return values[1] if len(values) > 1 else ""

        if isinstance(contact, (list, tuple)):
            return contact[1] if len(contact) > 1 else ""

        return contact.email
