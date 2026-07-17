"""HTML builder that takes pre-parsed EML content and personalizes it."""

from __future__ import annotations

import re


class HtmlEmailBuilder:
    """Build the final HTML email from pre-parsed .eml content.

    The html_body is expected to come from import_email_template.extract_from_eml(),
    with CID references already replaced by {{images[N]}} placeholders and {name}
    marking where the recipient's first name goes.
    """

    def __init__(self, html_body: str) -> None:
        self._html_body = html_body

    def build(self, first_name: str) -> str:
        html = self._html_body.replace("{name}", first_name)
        html = re.sub(r"\{images\[(\d+)\]\}", r"cid:image_\1", html)
        return html
