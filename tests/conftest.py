from __future__ import annotations

import os

# Unit test tidak boleh bergantung pada PostgreSQL lokal pengguna.
# Nilai environment ini dibaca sebelum app.database.db diimpor.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
