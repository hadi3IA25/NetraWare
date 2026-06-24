from __future__ import annotations

from pathlib import Path
from time import time
from typing import Iterable


DEFAULT_REPORT_EXTENSIONS = (".pdf", ".csv", ".png")


def cleanup_old_files(
    directory: str | Path,
    max_age_hours: int = 24,
    extensions: Iterable[str] = DEFAULT_REPORT_EXTENSIONS,
) -> int:
    """
    Menghapus file lama di dalam folder tertentu berdasarkan umur file.

    Fungsi ini aman digunakan untuk folder laporan karena:
    - hanya menghapus file dengan ekstensi tertentu;
    - tidak menghapus folder;
    - tidak menghapus database utama aplikasi;
    - tidak error jika folder belum ada.

    Parameter:
    - directory: lokasi folder yang akan dibersihkan.
    - max_age_hours: batas umur file dalam jam.
    - extensions: daftar ekstensi file yang boleh dihapus.

    Return:
    - jumlah file yang berhasil dihapus.
    """
    folder = Path(directory)

    if not folder.exists():
        return 0

    if not folder.is_dir():
        return 0

    allowed_extensions = {extension.lower() for extension in extensions}
    cutoff_time = time() - (max_age_hours * 3600)
    deleted_count = 0

    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in allowed_extensions:
            continue

        try:
            if file_path.stat().st_mtime < cutoff_time:
                file_path.unlink()
                deleted_count += 1
        except OSError:
            continue

    return deleted_count

