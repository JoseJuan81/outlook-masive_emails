"""Launch the FastAPI development server."""

import sys
from pathlib import Path

# Permite ejecutar este script con `uv run web/run.py` desde la raíz del
# proyecto: cuando Python corre un script, agrega a `sys.path` el directorio
# del propio script (no la raíz). Sin esta línea, uvicorn no podría importar
# el paquete `web` porque no sería visible desde `sys.path`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
