"""Port definition for contact repositories."""

from abc import ABC, abstractmethod

from domain.entities import ContactEntity
from domain.types import RawContact


class ContactRepositoryPort(ABC):
    """Contract for obtaining contacts from any source."""

    @abstractmethod
    def get_contacts(self) -> list[RawContact] | list[ContactEntity]:
        """Return contacts using the repository native shape."""
