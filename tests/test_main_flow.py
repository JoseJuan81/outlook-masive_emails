"""Tests del flujo de `main.run`: prepara los correos y escribe el staging JSON.

`main.run` NO envía por Outlook: arma un correo por contacto y escribe
`staging/emails_to_send.json` con la forma `[{"to", "subject", "html"}]`.
Estos tests ejercitan ese contrato real contra la producción actual, sin
dobles del builder: el `HtmlEmailBuilder` de verdad es el que personaliza
el HTML.
"""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path

import pytest

import main
from tests.durable_write import EspiaDurabilidad

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SUBJECT_FILE = _PROJECT_ROOT / "html" / "templates" / "subject.txt"

# Cuerpo mínimo con los dos placeholders del contrato: `{name}` (nombre del
# destinatario) y `{images[N]}` (imágenes inline que viajan como CID).
_CUERPO_DE_PRUEBA = (
    "<html><body>"
    "<p>Hola {name},</p>"
    '<img src="{images[0]}"/>'
    "<p>Atentamente, equipo de ventas</p>"
    "</body></html>"
)

# Contactos de mentira: el repositorio de Airtable queda sustituido por un doble.
CONTACTOS = [
    {"Nombre": "José Juan Domínguez", "Correo": "jose@example.com"},
    {"Nombre": "Ana López", "Correo": "ana@example.com"},
]


def _repo_para(contactos: list[dict]):
    """Devuelve un doble de `AirtableContactRepository` con los contactos dados."""

    class _Repo:
        def __init__(self, view: str | None = None) -> None:
            self.view = view

        def get_contacts(self) -> list[dict]:
            return [dict(contacto) for contacto in contactos]

    return _Repo


def _preparar(monkeypatch, tmp_path, contactos=CONTACTOS, respuesta="S") -> Path:
    """Deja `main.run` ejecutable sin red y devuelve la ruta del staging."""
    staging_file = tmp_path / "staging" / "emails_to_send.json"

    # El cuerpo real del repo no se toca: se usa uno de prueba con los mismos
    # placeholders, de modo que `_load_body()` siga siendo código de producción.
    body_file = tmp_path / "body_html.html"
    body_file.write_text(_CUERPO_DE_PRUEBA, encoding="utf-8")

    monkeypatch.setattr(main, "AirtableContactRepository", _repo_para(contactos))
    monkeypatch.setattr(main, "_BODY_FILE", body_file)
    monkeypatch.setattr(builtins, "input", lambda _: respuesta)
    monkeypatch.setattr(main, "_STAGING_FILE", staging_file)
    # La vista previa abre un navegador y pide una segunda confirmación: fuera.
    monkeypatch.delenv("PREVIEW_EMAIL_BEFORE_SEND", raising=False)
    monkeypatch.delenv("PREVIEW_OPEN_IN_BROWSER", raising=False)

    return staging_file


def _leer_staging(staging_file: Path) -> list[dict]:
    return json.loads(staging_file.read_text(encoding="utf-8"))


def _asunto_esperado() -> str:
    """El asunto se lee del repo, nunca se hardcodea en el test."""
    return _SUBJECT_FILE.read_text(encoding="utf-8").strip()


def test_main_run_escribe_un_correo_por_contacto_en_el_staging(monkeypatch, tmp_path):
    """Cada contacto produce una entrada con las claves exactas to/subject/html."""
    staging_file = _preparar(monkeypatch, tmp_path)

    main.run()

    assert staging_file.exists(), "main.run no escribió el fichero de staging"
    entradas = _leer_staging(staging_file)
    assert isinstance(entradas, list)
    assert len(entradas) == len(CONTACTOS)

    for entrada, contacto in zip(entradas, CONTACTOS):
        assert set(entrada.keys()) == {"to", "subject", "html"}
        assert entrada["to"] == contacto["Correo"]
        assert entrada["subject"] == _asunto_esperado()


def test_main_run_toma_el_asunto_del_fichero_subject_txt(monkeypatch, tmp_path):
    """El asunto sale de html/templates/subject.txt, no de un valor fijo en el código."""
    staging_file = _preparar(monkeypatch, tmp_path)

    main.run()

    entradas = _leer_staging(staging_file)
    assert all(entrada["subject"] == _asunto_esperado() for entrada in entradas)
    assert _asunto_esperado() != "", "subject.txt del repo está vacío"


def test_main_run_personaliza_el_html_con_el_nombre_del_contacto(monkeypatch, tmp_path):
    """El HTML final lleva el nombre real y ningún placeholder sin sustituir."""
    staging_file = _preparar(monkeypatch, tmp_path)

    main.run()

    entradas = _leer_staging(staging_file)
    html_primero = entradas[0]["html"]
    html_segundo = entradas[1]["html"]

    assert "José" in html_primero
    assert "Ana" in html_segundo
    assert "{name}" not in html_primero
    assert "{name}" not in html_segundo


def test_main_run_convierte_las_imagenes_placeholder_en_cid(monkeypatch, tmp_path):
    """`{images[N]}` viaja como `cid:image_N`: es lo que necesita Outlook COM."""
    staging_file = _preparar(monkeypatch, tmp_path)

    main.run()

    entradas = _leer_staging(staging_file)
    for entrada in entradas:
        assert "cid:image_0" in entrada["html"]
        assert "{images[" not in entrada["html"]


def test_main_run_con_test_email_manda_todo_a_un_destinatario(monkeypatch, tmp_path):
    """Con --test-email el staging tiene una sola entrada, toda ella al email de prueba."""
    staging_file = _preparar(monkeypatch, tmp_path)

    main.run(test_email="x@example.com")

    entradas = _leer_staging(staging_file)
    assert len(entradas) == 1
    assert entradas[0]["to"] == "x@example.com"
    assert all(entrada["to"] == "x@example.com" for entrada in entradas)
    assert entradas[0]["subject"] == _asunto_esperado()
    # Conserva el nombre del primer contacto para la personalización.
    assert "José" in entradas[0]["html"]


def test_main_run_sin_confirmacion_no_escribe_el_staging(monkeypatch, tmp_path):
    """Si el usuario no confirma, no se prepara ningún correo."""
    staging_file = _preparar(monkeypatch, tmp_path, respuesta="N")

    with pytest.raises(SystemExit):
        main.run()

    assert not staging_file.exists()


def test_main_run_sin_contactos_termina_con_error(monkeypatch, tmp_path):
    """Sin contactos no hay nada que preparar: error explícito y staging intacto."""
    staging_file = _preparar(monkeypatch, tmp_path, contactos=[])

    with pytest.raises(SystemExit):
        main.run()

    assert not staging_file.exists()


def test_main_run_sin_cuerpo_termina_con_error_accionable(monkeypatch, tmp_path):
    """Si el cuerpo del correo no existe, `main.run` lo dice y no prepara nada.

    Es la otra mitad del contrato de `_load_body()`: el error tiene que indicar
    qué comando ejecutar, no reventar con un TypeError.
    """
    staging_file = _preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "_BODY_FILE", tmp_path / "no_existe.html")

    with pytest.raises(SystemExit) as excinfo:
        main.run()

    mensaje = str(excinfo.value)
    assert "cuerpo" in mensaje.lower()
    assert "import_email_template.py" in mensaje
    assert not staging_file.exists()


def test_main_run_escribe_el_staging_con_flush_antes_del_fsync(monkeypatch, tmp_path):
    """El staging se escribe de forma durable: ``flush()`` y luego ``os.fsync()``.

    ``fh.flush()`` baja el buffer de Python al descriptor. Sin él, el
    ``os.fsync()`` sincroniza un fichero VACÍO y el staging se pierde: por eso
    el orden importa, no solo que ocurran.
    """
    staging_file = _preparar(monkeypatch, tmp_path)

    espia = EspiaDurabilidad(monkeypatch, main)

    main.run()

    assert espia.flushes() >= 1, (
        "main.run no hizo flush() del staging: los bytes pueden quedarse en "
        "el buffer de Python y el fsync sincronizaría un fichero vacío"
    )
    assert espia.fsyncs() >= 1, "main.run no hizo os.fsync() del staging"
    assert espia.nombres().index("flush") < espia.nombres().index("fsync"), (
        f"el flush() debe ocurrir antes del fsync(); eventos: {espia.nombres()}"
    )
    # Cuando se sincroniza, los bytes ya tienen que estar en el fichero.
    assert espia.tamanos_al_fsync()[0] > 0, (
        "en el momento del fsync el staging estaba vacío en disco: "
        "falta el fh.flush() que vuelca el buffer de Python al descriptor"
    )
    assert espia.inodos_al_fsync()[0] == os.stat(staging_file).st_ino, (
        "el fsync no se hizo sobre el fichero de staging"
    )
