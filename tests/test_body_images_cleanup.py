"""Tests del guardián de `html/images/body/`.

El directorio del cuerpo no contiene assets de fuente: `import_email_template.
save_images()` lo borra entero y reescribe `a.png`..`h.png`. Los PNG que hay
versionados en git son la salida de la última importación de EML.

Si la limpieza global de la suite lo deja vacío, cada `uv run pytest` borra del
árbol de trabajo los 8 PNG versionados y el envío real sale sin imágenes
(`send_from_staging.get_images()` devuelve `[]` sobre un directorio vacío).

Hoy la suite ya NO toca ese directorio: `clean_state` redirige las rutas de
escritura a `tmp_path`. Estos tests comprueban que:
  1. el mecanismo de snapshot/restore sigue funcionando sobre un directorio
     aislado (no toca el repo);
  2. el snapshot no es vacío cuando git versiona imágenes del cuerpo;
  3. el directorio real de imágenes existe;
  4. el ciclo real de la suite deja las imágenes versionadas en su sitio, sin
     borrar ni reponer nada del repositorio.
"""

from __future__ import annotations

from tests.conftest import (
    _BODY_IMAGES_DIR,
    _BODY_IMAGES_SNAPSHOT,
    _git_tracked_blobs,
    _restore_dir,
    _snapshot_dir,
    _wipe_dir,
)


def test_limpieza_restaura_las_imagenes_versionadas(tmp_path):
    """El mecanismo de snapshot/restore no puede dejar fuera los PNG."""
    cuerpo = tmp_path / "body"
    cuerpo.mkdir()
    (cuerpo / "a.png").write_bytes(b"\x89PNG\x0d\x0a\x1a\x0afalso")
    (cuerpo / "b.png").write_bytes(b"\x89PNG\x0d\x0a\x1a\x0afalso-2")

    snapshot = _snapshot_dir(cuerpo)
    assert snapshot == {
        "a.png": b"\x89PNG\x0d\x0a\x1a\x0afalso",
        "b.png": b"\x89PNG\x0d\x0a\x1a\x0afalso-2",
    }

    # Lo que hace la limpieza antes de cada test: el directorio queda vacío.
    _wipe_dir(cuerpo)
    assert _snapshot_dir(cuerpo) == {}

    # Lo que hace al terminar: el directorio vuelve a su estado original.
    _restore_dir(cuerpo, snapshot)
    assert _snapshot_dir(cuerpo) == snapshot


def test_el_snapshot_cubre_las_imagenes_versionadas_por_git():
    """Si git versiona imágenes del cuerpo, el snapshot debe poder restaurarlas."""
    versionadas = _git_tracked_blobs("html/images/body")

    faltan = set(versionadas) - set(_BODY_IMAGES_SNAPSHOT)
    assert not faltan, (
        "el snapshot de html/images/body está vacío o incompleto y la suite no "
        "podría restaurar las imágenes versionadas por git: "
        f"{sorted(faltan)} (versionadas: {sorted(versionadas)})"
    )


def test_el_directorio_de_imagenes_del_cuerpo_existe():
    """El directorio del cuerpo existe aunque no tenga ficheros dentro."""
    assert _BODY_IMAGES_DIR.exists(), (
        f"no existe el directorio de imágenes del cuerpo: {_BODY_IMAGES_DIR}"
    )
    assert _BODY_IMAGES_DIR.is_dir()


def test_el_ciclo_de_limpieza_deja_las_imagenes_versionadas(
    client, tmp_eml_factory, body_images_dir
):
    """La suite no puede modificar el directorio real de imágenes del cuerpo.

    Antes del aislamiento, `save_images()` escribía en `html/images/body/` del
    repo real y la limpieza de la suite lo borraba entero. Ahora el código bajo
    prueba escribe en un directorio temporal: el directorio real tiene que
    seguir byte a byte como estaba, y las imágenes versionadas tienen que
    seguir dentro.
    """
    antes = _snapshot_dir(_BODY_IMAGES_DIR)
    assert antes, (
        "html/images/body/ está vacío: no hay imágenes versionadas que preservar"
    )

    # El camino que antes tocaba el repo real: `save_images()` borra el
    # directorio de imágenes y escribe las nuevas.
    eml = tmp_eml_factory(subject="Caso A", n_images=2)
    resp = client.post(
        "/api/upload-eml",
        files={"file": ("a.eml", eml.read_bytes(), "message/rfc822")},
    )
    assert resp.status_code == 200, resp.text

    # La escritura fue al directorio temporal…
    assert len(list(body_images_dir.iterdir())) == 2
    # …y el directorio real quedó intacto.
    assert _snapshot_dir(_BODY_IMAGES_DIR) == antes, (
        "la suite modificó el directorio real de imágenes del cuerpo"
    )

    # Las imágenes versionadas siguen dentro.
    versionadas = set(_git_tracked_blobs("html/images/body"))
    presentes = {
        child.name for child in _BODY_IMAGES_DIR.iterdir() if child.is_file()
    }
    faltan = sorted(versionadas - presentes)
    assert not faltan, (
        "el ciclo de limpieza dejó fuera las imágenes versionadas del cuerpo: "
        f"{faltan}"
    )
