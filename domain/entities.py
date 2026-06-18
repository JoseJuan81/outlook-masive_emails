"""Core domain entities used by the application layer."""

from dataclasses import dataclass, field

from domain.types import MetadataMap


@dataclass(frozen=True)
class ContactEntity:
    """Normalized contact used by repositories and use cases."""

    name: str
    email: str
    metadata: MetadataMap = field(default_factory=dict)


@dataclass(frozen=True)
class EmailMessage:
    """Email payload sent through an email sender port."""

    subject: str
    to: str
    html_body: str
