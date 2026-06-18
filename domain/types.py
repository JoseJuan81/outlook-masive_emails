"""Shared type aliases and TypedDict models for the refactored architecture."""

from __future__ import annotations

from typing import Any, TypeAlias, TypedDict

ContactRecord = TypedDict(
    "ContactRecord",
    {
        "Nombre": str,
        "Correo": str,
        "Area": str,
        "NO Correo Masivo": bool,
        "País": str,
    },
    total=False,
)


MetadataMap: TypeAlias = dict[str, Any]
LegacyContact: TypeAlias = ContactRecord | tuple[str, str] | tuple[str, str, Any]
RawContact: TypeAlias = ContactRecord | tuple[Any, ...]
