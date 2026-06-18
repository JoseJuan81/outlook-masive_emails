"""HTML builder backed by the existing HtmlBody and HtmlBase classes."""

from __future__ import annotations

from Classes.base_class import HtmlBase
from Classes.body_class import HtmlBody
from ports.signature_provider_port import SignatureProviderPort


class HtmlEmailBuilder:
    """Build the final HTML email using the unchanged template classes.

    When no signature_provider is given the body_html.html is expected to
    already contain the full content (body + signature), which is the case
    when the template was imported from an EML/MSG file.
    """

    def __init__(self, signature_provider: SignatureProviderPort | None = None) -> None:
        self.signature_provider = signature_provider
        self._sign: str = ""
        self._body_builder = None
        self._base_builder = None

    def build_email(self) -> None:
        if self.signature_provider is not None:
            self._sign = self.signature_provider.get_signature()
        self._body_builder = HtmlBody().build()
        self._base_builder = HtmlBase().build()

    def build(self, first_name: str) -> str:
        if self._body_builder is None or self._base_builder is None:
            raise RuntimeError("Email builder has not been initialized.")
        body = self._body_builder(first_name)
        return self._base_builder(body, self._sign)
