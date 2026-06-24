from __future__ import annotations

import hashlib
from pathlib import Path

from app.core import model_manager


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_model_download_is_verified_and_cached(tmp_path: Path, monkeypatch):
    payload = b"verified-model-payload"
    destination = tmp_path / "face_landmarker.task"

    monkeypatch.setattr(model_manager, "MODEL_SIZE_BYTES", len(payload))
    monkeypatch.setattr(model_manager, "MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(
        model_manager.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    first = model_manager.ensure_face_landmarker_model(destination)
    second = model_manager.ensure_face_landmarker_model(destination)

    assert first == destination.resolve()
    assert second == destination.resolve()
    assert destination.read_bytes() == payload
