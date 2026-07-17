"""Launch the FastAPI development server."""

import os
import sys
from pathlib import Path

# Permite ejecutar este script con `uv run web/run.py` desde la raíz del
# proyecto: cuando Python corre un script, agrega a `sys.path` el directorio
# del propio script (no la raíz). Sin esta línea, uvicorn no podría importar
# el paquete `web` porque no sería visible desde `sys.path`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

URL = "http://localhost:8000"


def _supports_color() -> bool:
    """True si el terminal soporta secuencias ANSI / OSC 8."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _print_banner(url: str) -> None:
    """Imprime un banner con un link cliqueable a la UI.

    Usa hyperlinks OSC 8: en terminales modernos (Windows Terminal, iTerm2,
    GNOME Terminal 3.26+, Konsole, WezTerm) el texto se vuelve cliqueable y
    abre el navegador al hacer Ctrl+click. En terminales sin soporte cae a
    texto plano con la URL visible para copiar y pegar.
    """
    if not _supports_color():
        print()
        print("🚀  Masive Emails - Interface Web")
        print(f"    ➜  {url}")
        print("    (Press CTRL+C to stop)")
        print()
        return

    CYAN = "\033[1;36m"
    BLUE = "\033[1;34m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    # OSC 8: ESC ] 8 ; ; URL ESC \ TEXTO ESC ] 8 ; ; ESC \
    HYPERLINK = f"\033]8;;{url}\033\\{BLUE}{UNDERLINE}{url}{RESET}\033]8;;\033\\"

    print()
    print(f"{CYAN}🚀  Masive Emails - Interface Web{RESET}")
    print(f"    ➜  {HYPERLINK}")
    print(f"    {CYAN}(Press CTRL+C to stop){RESET}")
    print()


if __name__ == "__main__":
    _print_banner(URL)
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
