from __future__ import annotations

import hashlib
import os
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_SIZE_BYTES = 3_758_596
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "app" / "models" / "face_landmarker.task"


class ModelDownloadError(RuntimeError):
    """Raised when the MediaPipe Tasks model cannot be prepared safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_model(path: Path) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == MODEL_SIZE_BYTES
        and sha256_file(path) == MODEL_SHA256
    )


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def ensure_face_landmarker_model(model_path: Path | str = DEFAULT_MODEL_PATH) -> Path:
    """Return a verified Face Landmarker model, downloading it when absent.

    The download is written to a temporary file and moved atomically only after
    its size and SHA-256 checksum match the known official model bundle.
    """

    destination = Path(model_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if is_valid_model(destination):
        return destination

    if destination.exists():
        destination.unlink(missing_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix="face_landmarker_", suffix=".task.part", dir=destination.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)

    try:
        request = urllib.request.Request(
            MODEL_URL,
            headers={"User-Agent": "NetraWare/2.1"},
        )
        with urllib.request.urlopen(request, timeout=45, context=_ssl_context()) as response:
            with temporary_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

        if not is_valid_model(temporary_path):
            raise ModelDownloadError(
                "Model Face Landmarker berhasil diunduh, tetapi pemeriksaan integritas gagal."
            )

        temporary_path.replace(destination)
        return destination
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise ModelDownloadError(
            "Model Face Landmarker belum tersedia dan gagal diunduh otomatis. "
            "Pastikan perangkat terhubung ke internet, lalu jalankan "
            "`python scripts/download_model.py`."
        ) from exc
    finally:
        temporary_path.unlink(missing_ok=True)
