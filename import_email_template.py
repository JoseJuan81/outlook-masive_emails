"""Importa el cuerpo HTML de un archivo EML o MSG al template body_html.html."""

from __future__ import annotations

import argparse
import email
import email.header
import re
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent
BODY_TEMPLATE = _PROJECT_ROOT / "html/templates/body_html.html"
SUBJECT_FILE = _PROJECT_ROOT / "html/templates/subject.txt"
IMAGES_DIR = _PROJECT_ROOT / "html/images/body"
DOWNLOADS_DIR = Path("/mnt/c/Users/domin/Downloads")


def _decode_payload(payload: bytes, declared_charset: str | None) -> str:
    # Outlook frecuentemente declara iso-8859-1 pero envía UTF-8.
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode(declared_charset or "iso-8859-1", errors="replace")


def _decode_subject(raw: str | None) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def extract_from_eml(path: Path) -> tuple[str, str, dict[str, bytes]]:
    with open(path, "rb") as f:
        msg = email.message_from_bytes(f.read())

    subject = _decode_subject(msg.get("Subject"))
    html_body = ""
    inline_images: dict[str, bytes] = {}

    for part in msg.walk():
        content_type = part.get_content_type()
        cid = part.get("Content-ID", "").strip("<>")

        if content_type == "text/html" and not html_body:
            payload = part.get_payload(decode=True)
            html_body = _decode_payload(payload, part.get_content_charset())

        elif content_type.startswith("image/") and cid:
            inline_images[cid] = part.get_payload(decode=True)

    return subject, html_body, inline_images


def extract_from_msg(path: Path) -> tuple[str, str, dict[str, bytes]]:
    try:
        import extract_msg as em
    except ImportError:
        raise SystemExit(
            "Para archivos .msg ejecuta primero:  uv add extract-msg"
        )

    msg = em.Message(str(path))
    subject = msg.subject or ""
    html_body = msg.htmlBody or ""
    if isinstance(html_body, bytes):
        html_body = html_body.decode("utf-8", errors="replace")

    inline_images: dict[str, bytes] = {}
    for att in msg.attachments:
        cid = getattr(att, "cid", None) or getattr(att, "contentId", None) or ""
        cid = cid.strip("<>")
        if cid and hasattr(att, "data") and att.data:
            inline_images[cid] = att.data

    return subject, html_body, inline_images


def _detect_ext(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"GIF8":
        return "gif"
    return "png"


def ordered_cids_from_html(html: str, all_cids: set[str]) -> list[str]:
    """Devuelve los CIDs en el orden en que aparecen en el HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    seen: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.lower().startswith("cid:"):
            cid = src[4:].strip("<>")
            if cid in all_cids and cid not in seen:
                seen.append(cid)

    # Agrega CIDs del MIME que no aparecen en el HTML (por si acaso)
    for cid in all_cids:
        if cid not in seen:
            seen.append(cid)

    return seen


def save_images(inline_images: dict[str, bytes], ordered_cids: list[str]) -> dict[str, str]:
    """Guarda imágenes en html/images/body/ en orden de aparición y devuelve {cid: placeholder}."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for f in IMAGES_DIR.iterdir():
        if f.is_file():
            f.unlink()

    cid_to_placeholder: dict[str, str] = {}
    letters = "abcdefghijklmnopqrstuvwxyz"

    for idx, cid in enumerate(ordered_cids):
        data = inline_images[cid]
        letter = letters[idx] if idx < len(letters) else str(idx)
        filename = f"{letter}.{_detect_ext(data)}"
        (IMAGES_DIR / filename).write_bytes(data)
        placeholder = "{{images[{}]}}".format(idx)
        cid_to_placeholder[cid] = placeholder
        print(f"  Imagen guardada: html/images/body/{filename}  →  {{images[{idx}]}}")

    return cid_to_placeholder


def replace_cids(html: str, cid_map: dict[str, str]) -> str:
    for cid, placeholder in cid_map.items():
        html = re.sub(
            rf"cid:{re.escape(cid)}", placeholder, html, flags=re.IGNORECASE
        )
    return html


def extract_body_content(full_html: str) -> str:
    """Extrae solo el contenido interno del <body>."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(full_html, "html.parser")
    body = soup.find("body")
    return body.decode_contents() if body else full_html


def find_latest_in_downloads() -> Path:
    """Devuelve el archivo .eml o .msg más reciente en la carpeta Descargas de Windows."""
    if not DOWNLOADS_DIR.exists():
        raise SystemExit(f"No se encontró la carpeta de Descargas: {DOWNLOADS_DIR}")

    candidates = [
        f for f in DOWNLOADS_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in (".eml", ".msg")
    ]
    if not candidates:
        raise SystemExit(
            f"No se encontraron archivos .eml o .msg en:\n  {DOWNLOADS_DIR}"
        )

    latest = max(candidates, key=lambda f: f.stat().st_mtime)
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa el cuerpo de un .eml o .msg al template body_html.html"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help=(
            "Ruta al archivo .eml o .msg. "
            "Si se omite, se usa el más reciente de C:/Users/domin/Downloads/"
        ),
    )
    args = parser.parse_args()

    if args.file is None:
        path = find_latest_in_downloads()
        print(f"Usando archivo más reciente de Descargas: {path.name}")
    else:
        candidate = Path(args.file)
        # Si no incluye directorio, buscar en Descargas
        if candidate.parent == Path(".") and not candidate.exists():
            candidate = DOWNLOADS_DIR / candidate
        path = candidate
        if not path.exists():
            raise SystemExit(f"Archivo no encontrado: {path}")

    ext = path.suffix.lower()
    if ext == ".eml":
        subject, html, inline_images = extract_from_eml(path)
    elif ext == ".msg":
        subject, html, inline_images = extract_from_msg(path)
    else:
        raise SystemExit(f"Formato no soportado: {ext}. Usa .eml o .msg")

    print(f"\nArchivo procesado: {path.name}")
    print(f"Asunto: {subject}")
    print(f"Imágenes inline encontradas: {len(inline_images)}")

    if inline_images:
        ordered = ordered_cids_from_html(html, set(inline_images.keys()))
        cid_map = save_images(inline_images, ordered)
        html = replace_cids(html, cid_map)

    body_content = extract_body_content(html)
    BODY_TEMPLATE.write_text(body_content, encoding="utf-8")
    SUBJECT_FILE.write_text(subject, encoding="utf-8")

    print(f"\nTemplates guardados en: html/templates/")
    print("\nPROXIMO PASO:")
    print('  Abre html/templates/body_html.html y reemplaza el nombre del destinatario')
    print('  con {name}. Ejemplo: "Hola José" → "Hola {name}"')
    print("\nLuego verifica con: uv run preview.py --name 'TuNombre'")


if __name__ == "__main__":
    main()
