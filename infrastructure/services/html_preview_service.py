"""Service for generating a local HTML preview before sending emails."""

from __future__ import annotations

import base64
import re
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BODY_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"


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
        """Convert cid:image_N references to base64 data URIs for browser rendering."""
        image_paths = self._get_body_images()

        def replace(m: re.Match) -> str:
            idx = int(m.group(1))
            if idx < len(image_paths):
                return f'src="{self._to_data_uri(image_paths[idx])}"'
            return m.group(0)

        return re.sub(r'src="cid:image_(\d+)"', replace, html)

    @staticmethod
    def _get_body_images() -> list[Path]:
        if not _BODY_IMAGES_DIR.exists():
            return []
        return sorted(
            (f for f in _BODY_IMAGES_DIR.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
            key=lambda f: f.name,
        )

    @staticmethod
    def _to_data_uri(path: Path) -> str:
        ext = path.suffix.lstrip(".").lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext, "image/png")
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
