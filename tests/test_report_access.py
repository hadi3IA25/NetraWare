from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.report import verify_report_access


def test_report_access_is_open_when_token_is_not_configured(monkeypatch):
    monkeypatch.delenv("REPORT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_EXPORT_TOKEN", raising=False)

    verify_report_access()


def test_report_access_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("REPORT_ACCESS_TOKEN", "secret-token")
    monkeypatch.delenv("ADMIN_EXPORT_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        verify_report_access(access_key="wrong-token")

    assert exc.value.status_code == 403


def test_report_access_accepts_query_and_header_token(monkeypatch):
    monkeypatch.setenv("REPORT_ACCESS_TOKEN", "secret-token")
    monkeypatch.delenv("ADMIN_EXPORT_TOKEN", raising=False)

    verify_report_access(access_key="secret-token")
    verify_report_access(x_report_token="secret-token")


def test_report_access_supports_legacy_admin_token(monkeypatch):
    monkeypatch.delenv("REPORT_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_EXPORT_TOKEN", "legacy-token")

    verify_report_access(admin_key="legacy-token")
