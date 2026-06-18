"""Signature provider backed by the existing HtmlSign class."""

from Classes.sign_class import HtmlSign
from ports.signature_provider_port import SignatureProviderPort


class HtmlSignatureProvider(SignatureProviderPort):
    """Reuse the current signature generation exactly as it exists today."""

    def get_signature(self) -> str:
        return HtmlSign().build()
