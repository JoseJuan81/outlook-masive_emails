"""FastAPI application for the mass email sender UI."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from env import load_project_env
from import_email_template import (
    extract_from_eml,
    extract_from_msg,
    extract_body_content,
    ordered_cids_from_html,
    save_images,
    replace_cids,
)
from infrastructure.services.html_email_builder import HtmlEmailBuilder
from infrastructure.services.logging_config import setup_logging

load_project_env()
setup_logging()
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BODY_IMAGES_DIR = _PROJECT_ROOT / "html" / "images" / "body"
_STAGING_FILE = _PROJECT_ROOT / "staging" / "emails_to_send.json"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="Masive Emails")

app.mount("/images/body", StaticFiles(directory=str(_BODY_IMAGES_DIR)), name="body_images")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

# --- In-memory state for the current session ---
_session: dict = {
    "subject": None,
    "html_body": None,
    "builder": None,
}


def _resolve_images_for_preview(html: str) -> str:
    """Replace {{images[N]}} placeholders with /images/body/ URLs for browser preview."""
    images = sorted(
        (f for f in _BODY_IMAGES_DIR.iterdir() if f.is_file() and not f.name.endswith(".Identifier")),
        key=lambda f: f.name,
    ) if _BODY_IMAGES_DIR.exists() else []

    def replace(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx < len(images):
            return f"/images/body/{images[idx].name}"
        return m.group(0)

    html = re.sub(r"\{images\[(\d+)\]\}", replace, html)
    html = re.sub(r"cid:image_(\d+)", replace, html)
    return html


# --- Endpoints ---


@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = _TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found. Create web/templates/index.html")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/upload-eml")
async def upload_eml(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".eml", ".msg"):
        raise HTTPException(status_code=400, detail="Only .eml and .msg files are supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if ext == ".eml":
            subject, html, inline_images = extract_from_eml(tmp_path)
        else:
            subject, html, inline_images = extract_from_msg(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if inline_images:
        ordered = ordered_cids_from_html(html, set(inline_images.keys()))
        cid_map = save_images(inline_images, ordered)
        html = replace_cids(html, cid_map)

    body_content = extract_body_content(html)

    _session["subject"] = subject
    _session["html_body"] = body_content
    _session["builder"] = HtmlEmailBuilder(body_content)

    logger.info("EML cargado -> subject=%r, images=%d", subject, len(inline_images))

    return {
        "subject": subject,
        "images_count": len(inline_images),
        "filename": file.filename,
    }


@app.get("/api/preview")
async def preview():
    if not _session["html_body"]:
        raise HTTPException(status_code=400, detail="No email loaded. Upload an .eml first.")

    builder = _session["builder"]
    preview_html = builder.build("Juan")
    preview_html = _resolve_images_for_preview(preview_html)

    return {
        "html": preview_html,
        "subject": _session["subject"],
    }


@app.get("/api/sources")
async def list_sources():
    return [
        {"id": "airtable", "name": "Airtable", "has_views": True},
        {"id": "notion", "name": "Notion", "has_views": True},
        {"id": "csv", "name": "CSV", "has_views": False},
        {"id": "supabase", "name": "Supabase", "has_views": False},
    ]


@app.get("/api/sources/{source_id}/views")
async def list_views(source_id: str):
    if source_id == "airtable":
        return _get_airtable_views()
    elif source_id == "notion":
        return _get_notion_views()
    else:
        raise HTTPException(status_code=400, detail=f"Source '{source_id}' does not support views")


def _get_airtable_views() -> list[dict]:
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_id = os.getenv("AIRTABLE_CONTACT_TABLE_ID")
    token = os.getenv("AIRTABLE_TOKEN")

    if not all([base_id, table_id, token]):
        return [{"id": "default", "name": "Vista por defecto"}]

    try:
        import requests
        url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        for table in resp.json().get("tables", []):
            if table.get("id") == table_id or table.get("name") == table_id:
                views = table.get("views", [])
                return [{"id": v["id"], "name": v["name"]} for v in views]

        return [{"id": "default", "name": "Vista por defecto"}]
    except Exception as e:
        logger.warning("Could not fetch Airtable views: %s", e)
        default_view = os.getenv("AIRTABLE_VIEW")
        if default_view:
            return [{"id": default_view, "name": default_view}]
        return [{"id": "default", "name": "Vista por defecto"}]


def _get_notion_views() -> list[dict]:
    """Return Notion filter options. Notion doesn't have 'views' like Airtable,
    so we return filter column options that the repository supports."""
    return [
        {"id": "all", "name": "Todos los contactos"},
        {"id": "mexico", "name": "México"},
        {"id": "colombia", "name": "Colombia"},
        {"id": "peru", "name": "Perú"},
    ]


@app.get("/api/sources/{source_id}/contacts")
async def list_contacts(source_id: str, view: str | None = None):
    try:
        repo = _build_repository(source_id, view)
        raw_contacts = repo.get_contacts()
    except Exception as e:
        logger.error("Error loading contacts from %s: %s", source_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    contacts = []
    for c in raw_contacts:
        if isinstance(c, dict):
            contacts.append({
                "name": c.get("Nombre", ""),
                "email": c.get("Correo", ""),
            })
        else:
            contacts.append({"name": c.name, "email": c.email})

    return {"contacts": contacts, "total": len(contacts)}


def _build_repository(source_id: str, view: str | None):
    if source_id == "airtable":
        from infrastructure.repositories.airtable_contact_repository import AirtableContactRepository
        effective_view = view if view and view != "default" else None
        return AirtableContactRepository(view=effective_view)

    elif source_id == "notion":
        from infrastructure.repositories.notion_contact_repository import NotionContactRepository
        filters = [] if not view or view == "all" else [view]
        return NotionContactRepository(filter_columns=filters)

    elif source_id == "csv":
        from infrastructure.repositories.csv_contact_repository import CSVContactRepository
        return CSVContactRepository()

    elif source_id == "supabase":
        from infrastructure.repositories.supabase_contact_repository import SupabaseContactRepository
        return SupabaseContactRepository()

    raise HTTPException(status_code=400, detail=f"Unknown source: {source_id}")


_PROGRESS_FILE = _PROJECT_ROOT / "staging" / "send_progress.json"
_send_process = None


@app.post("/api/send")
async def send_emails(payload: dict):
    global _send_process

    if not _session["builder"]:
        raise HTTPException(status_code=400, detail="No email loaded. Upload an .eml first.")

    source_id = payload.get("source")
    view = payload.get("view")
    test_email = payload.get("test_email")

    if not source_id:
        raise HTTPException(status_code=400, detail="Source is required")

    try:
        repo = _build_repository(source_id, view)
        raw_contacts = repo.get_contacts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading contacts: {e}")

    if not raw_contacts:
        raise HTTPException(status_code=400, detail="No contacts found")

    builder = _session["builder"]
    subject = _session["subject"]

    emails = []
    for c in raw_contacts:
        if isinstance(c, dict):
            name = c.get("Nombre", "")
            email_addr = c.get("Correo", "")
        else:
            name = c.name
            email_addr = c.email

        if test_email:
            email_addr = test_email

        first_name = name.split()[0].title() if name else "Estimado"
        html_body = builder.build(first_name)

        emails.append({
            "to": email_addr,
            "subject": subject,
            "html": html_body,
        })

        if test_email:
            break

    _STAGING_FILE.parent.mkdir(exist_ok=True)
    _STAGING_FILE.write_text(json.dumps(emails, ensure_ascii=False, indent=2), encoding="utf-8")

    # Clean previous progress
    _PROGRESS_FILE.unlink(missing_ok=True)

    logger.info("Staging ready -> %d emails, launching send process", len(emails))

    send_script = _PROJECT_ROOT / "send_from_staging.py"
    win_python = "/mnt/c/Python313/python.exe"
    win_script = subprocess.run(
        ["wslpath", "-w", str(send_script)], capture_output=True, text=True
    ).stdout.strip()

    _send_process = subprocess.Popen(
        [win_python, win_script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(_PROJECT_ROOT),
    )

    return {"total": len(emails), "message": "Envío iniciado"}


@app.get("/api/send/progress")
async def send_progress():
    global _send_process

    if not _PROGRESS_FILE.exists():
        return {"status": "waiting", "total": 0, "current": 0, "sent": 0, "failed": 0}

    progress = json.loads(_PROGRESS_FILE.read_text(encoding="utf-8"))

    # If process finished, collect its output
    if progress.get("status") == "complete" and _send_process is not None:
        _send_process.wait()
        stdout = _send_process.stdout.read().decode("utf-8", errors="replace").strip()
        logger.info("Send process finished: %s", stdout)
        _send_process = None

    return progress
