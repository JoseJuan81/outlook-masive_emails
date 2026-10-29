"""Instrumentación de la escritura del staging para auditar su DURABILIDAD.

El camino de envío real escribe el staging y lo da por bueno:

* ``web/app.py`` -> ``_write_staging_file()``: ``write`` + ``flush`` + ``os.fsync``
* ``main.py``    -> ``run()``:                   ``write`` + ``flush`` + ``os.fsync``

``flush()`` no es decorativo: baja el buffer de Python al descriptor. Sin él,
``os.fsync()`` sincroniza un fichero VACÍO y el staging se pierde.

La espía NO sustituye el comportamiento bajo prueba: el ``write``, el
``flush()`` y el ``os.fsync()`` reales se ejecutan tal cual. Solo se observan:

* cada llamada a ``flush()`` (con el descriptor del fichero),
* cada llamada a ``os.fsync()`` (con el tamaño y el inodo que el SO ve en ese
  instante).

Con las dos señales se puede comprobar que el flush ocurre ANTES del fsync y
que, cuando el fsync ocurre, los bytes ya están en el fichero.
"""

from __future__ import annotations

import os
from typing import Any


class _FicheroEspia:
    """Proxy de un fichero que registra las llamadas a ``flush()``."""

    def __init__(self, real, eventos: list[tuple[str, Any]]) -> None:
        self._real = real
        self._eventos = eventos

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._real.__exit__(*exc_info)

    def __getattr__(self, nombre: str):
        return getattr(self._real, nombre)

    def flush(self) -> None:
        self._eventos.append(("flush", self._real.fileno()))
        self._real.flush()


class EspiaDurabilidad:
    """Instrumenta la escritura de ficheros de un módulo.

    Uso::

        espia = EspiaDurabilidad(monkeypatch, main)
        main.run()
        assert espia.flushes() == 1
        assert espia.tamanos_al_fsync()[0] > 0

    ``modulo`` es el módulo cuyo ``open()`` se sustituye por un proxy que
    registra los ``flush()``. El ``os.fsync`` se espía globalmente porque los
    dos módulos de producción lo llaman como ``os.fsync(...)``.
    """

    def __init__(self, monkeypatch, modulo) -> None:
        self.eventos: list[tuple[str, Any]] = []
        self._modulo = modulo
        self._open_real = open
        self._fsync_real = os.fsync

        def fake_open(ruta, *args, **kwargs):
            return _FicheroEspia(self._open_real(ruta, *args, **kwargs), self.eventos)

        def spy_fsync(fd):
            estado = os.fstat(fd)
            self.eventos.append(("fsync", (estado.st_size, estado.st_ino)))
            return self._fsync_real(fd)

        monkeypatch.setattr(modulo, "open", fake_open, raising=False)
        monkeypatch.setattr(os, "fsync", spy_fsync)

    def nombres(self) -> list[str]:
        """Nombre de cada evento, en orden de aparición."""
        return [nombre for nombre, _ in self.eventos]

    def flushes(self) -> int:
        """Número de llamadas a ``flush()``."""
        return self.nombres().count("flush")

    def fsyncs(self) -> int:
        """Número de llamadas a ``os.fsync()``."""
        return self.nombres().count("fsync")

    def tamanos_al_fsync(self) -> list[int]:
        """Tamaño que el SO tenía del fichero en cada ``os.fsync()``."""
        return [datos[0] for nombre, datos in self.eventos if nombre == "fsync"]

    def inodos_al_fsync(self) -> list[int]:
        """Inodo del fichero sincronizado en cada ``os.fsync()``."""
        return [datos[1] for nombre, datos in self.eventos if nombre == "fsync"]
