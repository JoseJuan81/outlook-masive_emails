"""Service for generating a local HTML preview before sending emails."""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path

from Classes.base64_converter import Base64Converter
from Classes.body_class import HtmlBody


class HtmlPreviewService:
    """Persist a rendered email preview to disk and optionally open it."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path("preview")

    def generate_preview(
        self,
        html: str,
        filename: str = "email_preview.html",
        open_in_browser: bool = False,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = self.output_dir / filename
        preview_path.write_text(self._cids_to_base64(html), encoding="utf-8")

        if open_in_browser:
            webbrowser.open(preview_path.resolve().as_uri())

        return preview_path

    def _cids_to_base64(self, html: str) -> str:
        """Convierte referencias cid:image_N a data URIs para renderizado en browser."""
        image_paths = HtmlBody().image_paths

        def replace(m: re.Match) -> str:
            idx = int(m.group(1))
            if idx < len(image_paths):
                return f'src="{Base64Converter.convert_to_bs64(image_paths[idx])}"'
            return m.group(0)

        return re.sub(r'src="cid:image_(\d+)"', replace, html)
