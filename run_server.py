"""Entry point para Uvicorn (Docker CMD y ejecución local)."""

import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("UVICORN_RELOAD", "false").lower() in ("1", "true", "yes")

    uvicorn.run("main:app", host=host, port=port, reload=reload)
