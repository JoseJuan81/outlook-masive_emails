"""Port definition for signature providers."""

from abc import ABC, abstractmethod


class SignatureProviderPort(ABC):
    """Contract for obtaining the HTML signature."""

    @abstractmethod
    def get_signature(self) -> str:
        """Return the email signature HTML."""
