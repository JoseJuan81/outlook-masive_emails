"""Port definition for email senders."""

from abc import ABC, abstractmethod

from domain.entities import EmailMessage


class EmailSenderPort(ABC):
    """Contract for sending emails through any provider."""

    @abstractmethod
    def send(self, email: EmailMessage) -> None:
        """Send an email message."""
