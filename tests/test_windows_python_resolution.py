"""Tests de la resolución del intérprete de Python de Windows (``web/app.py``).

Contexto
--------
``_resolve_windows_python()`` construía antes su lista de candidatos
SUSTITUYENDO en sitio el placeholder ``/USER/`` por el usuario de WSL::

    candidates = [c.replace("/USER/", f"/{user}/") for c in candidates]

Eso descartaba las rutas literales. En una máquina cuya carpeta de perfil de
Windows se llama literalmente ``USER``
(``/mnt/c/Users/USER/AppData/Local/Programs/Python/Python313/python.exe``) la
única ruta real quedaba fuera de la lista y la resolución devolvía ``None``
salvo que existiera ``WINDOWS_PYTHON_PATH``.

El fix parte la lista en dos mitades (``_candidate_windows_python_paths()``):
las rutas literales se CONSERVAN y las sustituidas se AÑADEN.

Determinismo
------------
Estos tests no dependen de la máquina: no tocan el mount real ``/mnt/c``.
La decisión de "qué candidato existe" la toma el test, no el host: se parchea
``pathlib.Path.is_file`` y ``monkeypatch`` lo restaura al final del test.
El caso del override explícito usa un fichero real dentro de ``tmp_path``.
"""

from __future__ import annotations

import pathlib

from web import app as web_app

# Placeholder que usa web/app.py para la carpeta de perfil de Windows.
PLACEHOLDER = "USER"

# Usuario WSL deliberadamente DISTINTO del placeholder, para que la ruta
# literal y la ruta sustituida sean distinguibles sin depender de la máquina.
OTHER_USER = "wsl_user_test"

# Ruta literal de una instalación por usuario bajo AppData.
LITERAL_PROFILE_PATH = (
    "/mnt/c/Users/USER/AppData/Local/Programs/Python/Python313/python.exe"
)

# Instalación "para todos los usuarios" en la raíz de C:.
SYSTEM_PYTHON_PATH = "/mnt/c/Python313/python.exe"


def _only_existing(*existentes: str):
    """Devuelve un ``Path.is_file`` que solo da ``True`` para esas rutas.

    Se compara con ``as_posix()`` porque las rutas candidatas de ``web/app.py``
    están escritas con separadores ``/``, que ``Path`` conserva tal cual en
    Linux. La comparación es exacta: cualquier otra ruta da ``False``, así que
    el resultado no depende de lo que haya montado en ``/mnt/c``.
    """
    objetivo = set(existentes)

    def fake_is_file(self) -> bool:
        return self.as_posix() in objetivo

    return fake_is_file


def _substituida(ruta: str, usuario: str) -> str:
    """Variante de una ruta literal con el placeholder sustituido."""
    return ruta.replace(f"/Users/{PLACEHOLDER}/", f"/Users/{usuario}/")


# ---------------------------------------------------------------------------
# _candidate_windows_python_paths(): la lista de candidatos
# ---------------------------------------------------------------------------


def test_candidates_sin_user_no_incluyen_variantes_sustituidas(monkeypatch):
    """Sin ``USER`` en el entorno la lista solo trae rutas literales.

    Si se sustituyera el placeholder con una cadena vacía, aparecerían rutas
    del tipo ``/mnt/c/Users//AppData/...``: aquí no puede haber ninguna.
    """
    monkeypatch.delenv("USER", raising=False)

    candidatos = web_app._candidate_windows_python_paths()

    assert candidatos, "la lista de candidatos no puede estar vacía"
    for ruta in candidatos:
        assert "/Users/USER/" in ruta or "/Users/" not in ruta, (
            "aparece una variante de perfil sustituida sin que USER esté "
            f"definido: {ruta}"
        )


def test_candidates_sin_user_coinciden_con_el_subconjunto_literal(monkeypatch):
    """Sin ``USER``, la lista es exactamente el subconjunto literal.

    La comparación es relacional: se toma la lista con un usuario conocido y
    se descarta la parte sustituida. Lo que queda debe ser, elemento a
    elemento, la lista que se obtiene sin ``USER``.
    """
    monkeypatch.setenv("USER", OTHER_USER)
    con_usuario = list(web_app._candidate_windows_python_paths())

    monkeypatch.delenv("USER", raising=False)
    sin_usuario = list(web_app._candidate_windows_python_paths())

    literales = [
        ruta for ruta in con_usuario if f"/Users/{OTHER_USER}/" not in ruta
    ]
    assert literales, "no se encontró ninguna ruta literal que comparar"
    assert sin_usuario == literales, (
        "sin USER la lista debería contener solo las rutas literales; "
        f"sobran: {[r for r in sin_usuario if r not in literales]} "
        f"faltan: {[r for r in literales if r not in sin_usuario]}"
    )


def test_candidates_con_user_conservan_la_ruta_literal(monkeypatch):
    """La ruta literal ``/mnt/c/Users/USER/...`` no se descarta.

    Este es el corazón del bug: al sustituir en sitio, la variante literal
    desaparecía de la lista.
    """
    monkeypatch.setenv("USER", OTHER_USER)

    candidatos = web_app._candidate_windows_python_paths()

    assert LITERAL_PROFILE_PATH in candidatos, (
        "la ruta literal se perdió al añadir las variantes sustituidas: "
        f"{LITERAL_PROFILE_PATH}"
    )


def test_candidates_con_user_anaden_la_variante_sustituida(monkeypatch):
    """Con ``USER`` definido aparece además la variante sustituida."""
    monkeypatch.setenv("USER", OTHER_USER)

    candidatos = web_app._candidate_windows_python_paths()

    sustituida = _substituida(LITERAL_PROFILE_PATH, OTHER_USER)
    assert sustituida in candidatos, (
        f"falta la variante sustituida: {sustituida}"
    )
    assert candidatos.index(LITERAL_PROFILE_PATH) < candidatos.index(sustituida), (
        "la ruta literal debe ir antes que su variante sustituida"
    )


def test_candidates_con_user_incluyen_la_contravariante_de_cada_literal(
    monkeypatch,
):
    """Cada ruta de perfil literal tiene su variante sustituida."""
    monkeypatch.setenv("USER", OTHER_USER)

    candidatos = web_app._candidate_windows_python_paths()

    for ruta in candidatos:
        if f"/Users/{PLACEHOLDER}/" in ruta:
            contra = _substituida(ruta, OTHER_USER)
            assert contra in candidatos, (
                f"falta la variante sustituida de {ruta}: {contra}"
            )


def test_candidates_sin_duplicados_cuando_user_coincide_con_el_placeholder(
    monkeypatch,
):
    """``USER="USER"``: la sustitución no debe duplicar rutas."""
    monkeypatch.setenv("USER", PLACEHOLDER)

    candidatos = web_app._candidate_windows_python_paths()

    assert len(candidatos) == len(set(candidatos)), (
        "hay rutas repetidas: "
        f"{sorted({r for r in candidatos if candidatos.count(r) > 1})}"
    )
    assert candidatos.count(LITERAL_PROFILE_PATH) == 1


def test_candidates_sin_duplicados_con_usuario_distinto(monkeypatch):
    """Con un usuario distinto del placeholder tampoco hay repetidos."""
    monkeypatch.setenv("USER", OTHER_USER)

    candidatos = web_app._candidate_windows_python_paths()

    assert len(candidatos) == len(set(candidatos))


# ---------------------------------------------------------------------------
# _resolve_windows_python(): la resolución
# ---------------------------------------------------------------------------


def test_resolve_devuelve_el_valor_explicito_de_windows_python_path(
    tmp_path, monkeypatch
):
    """``WINDOWS_PYTHON_PATH`` válido: se devuelve exactamente ese valor."""
    interprete = tmp_path / "python.exe"
    interprete.write_bytes(b"MZ")

    monkeypatch.setenv("WINDOWS_PYTHON_PATH", str(interprete))

    assert web_app._resolve_windows_python() == str(interprete)


def test_resolve_sin_override_devuelve_el_candidato_literal_existente(
    monkeypatch,
):
    """Sin override, devuelve el primer candidato que existe.

    El candidato que "existe" es la ruta LITERAL de perfil: es justamente la
    que el bug descartaba.
    """
    monkeypatch.delenv("WINDOWS_PYTHON_PATH", raising=False)
    monkeypatch.setenv("USER", OTHER_USER)
    monkeypatch.setattr(
        pathlib.Path, "is_file", _only_existing(LITERAL_PROFILE_PATH)
    )

    assert web_app._resolve_windows_python() == LITERAL_PROFILE_PATH


def test_resolve_encuentra_la_variante_sustituida(monkeypatch):
    """La variante sustituida también es alcanzable por la resolución."""
    monkeypatch.delenv("WINDOWS_PYTHON_PATH", raising=False)
    monkeypatch.setenv("USER", OTHER_USER)
    sustituida = _substituida(LITERAL_PROFILE_PATH, OTHER_USER)
    monkeypatch.setattr(pathlib.Path, "is_file", _only_existing(sustituida))

    assert web_app._resolve_windows_python() == sustituida


def test_resolve_devuelve_el_primer_candidato_existente_en_orden_de_lista(
    monkeypatch,
):
    """Si existen varios candidatos, gana el primero en el orden de la lista."""
    monkeypatch.delenv("WINDOWS_PYTHON_PATH", raising=False)
    monkeypatch.setenv("USER", OTHER_USER)
    posteriores = (
        LITERAL_PROFILE_PATH,
        _substituida(LITERAL_PROFILE_PATH, OTHER_USER),
    )
    monkeypatch.setattr(
        pathlib.Path,
        "is_file",
        _only_existing(SYSTEM_PYTHON_PATH, *posteriores),
    )

    assert web_app._resolve_windows_python() == SYSTEM_PYTHON_PATH


def test_resolve_ignora_un_windows_python_path_inexistente(tmp_path, monkeypatch):
    """Un override que no es un fichero no invalida los candidatos."""
    monkeypatch.setenv(
        "WINDOWS_PYTHON_PATH", str(tmp_path / "no_existe" / "python.exe")
    )
    monkeypatch.setenv("USER", OTHER_USER)
    monkeypatch.setattr(
        pathlib.Path, "is_file", _only_existing(LITERAL_PROFILE_PATH)
    )

    assert web_app._resolve_windows_python() == LITERAL_PROFILE_PATH


def test_resolve_sin_ningun_candidato_devuelve_none(monkeypatch):
    """Si no existe ningún candidato, la resolución devuelve ``None``."""
    monkeypatch.delenv("WINDOWS_PYTHON_PATH", raising=False)
    monkeypatch.setenv("USER", OTHER_USER)
    monkeypatch.setattr(pathlib.Path, "is_file", _only_existing())

    assert web_app._resolve_windows_python() is None


def test_resolve_sin_user_y_sin_candidatos_devuelve_none(monkeypatch):
    """Sin ``USER`` y sin candidatos, la resolución devuelve ``None``."""
    monkeypatch.delenv("WINDOWS_PYTHON_PATH", raising=False)
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.setattr(pathlib.Path, "is_file", _only_existing())

    assert web_app._resolve_windows_python() is None
