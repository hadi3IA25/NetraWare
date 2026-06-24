"""Jalankan seluruh aplikasi dengan: python app.py"""

from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent


def open_local_browser(url: str) -> None:
    if not os.getenv("PORT") and os.getenv("OPEN_BROWSER", "1") != "0":
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    port = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
    host = os.getenv("APP_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    open_local_browser(f"http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
