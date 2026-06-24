import pytest

from app.core.metrics import (
    calculate_ear,
    calculate_average_ear,
    calculate_perclos,
    calculate_blink_rate,
    remove_outliers_iqr,
    normalize_score,
    clamp,
)


def test_calculate_ear_for_open_eye():
    """
    Menguji EAR pada kondisi mata terbuka.

    Titik dibuat secara manual:
    - Jarak vertikal 1 = 2
    - Jarak vertikal 2 = 2
    - Jarak horizontal = 4

    EAR = (2 + 2) / (2 * 4) = 0.5
    """
    eye_points = [
        (0.0, 0.0),    # p1
        (1.0, 1.0),    # p2
        (3.0, 1.0),    # p3
        (4.0, 0.0),    # p4
        (3.0, -1.0),   # p5
        (1.0, -1.0),   # p6
    ]

    ear = calculate_ear(eye_points)

    assert ear == pytest.approx(0.5, abs=1e-6)


def test_calculate_ear_for_closed_eye():
    """
    Menguji EAR pada kondisi mata hampir tertutup.

    Jarak vertikal dibuat kecil sehingga nilai EAR juga kecil.
    """
    eye_points = [
        (0.0, 0.0),
        (1.0, 0.1),
        (3.0, 0.1),
        (4.0, 0.0),
        (3.0, -0.1),
        (1.0, -0.1),
    ]

    ear = calculate_ear(eye_points)

    assert ear == pytest.approx(0.05, abs=1e-6)
    assert ear < 0.20


def test_calculate_ear_requires_six_points():
    """
    EAR harus dihitung dari 6 titik landmark mata.
    Jika kurang atau lebih, sistem harus memberi error.
    """
    invalid_points = [
        (0.0, 0.0),
        (1.0, 1.0),
    ]

    with pytest.raises(ValueError):
        calculate_ear(invalid_points)


def test_calculate_average_ear():
    """
    Menguji rata-rata EAR dari mata kiri dan mata kanan.
    """
    left_eye = [
        (0.0, 0.0),
        (1.0, 1.0),
        (3.0, 1.0),
        (4.0, 0.0),
        (3.0, -1.0),
        (1.0, -1.0),
    ]

    right_eye = [
        (0.0, 0.0),
        (1.0, 0.8),
        (3.0, 0.8),
        (4.0, 0.0),
        (3.0, -0.8),
        (1.0, -0.8),
    ]

    avg_ear = calculate_average_ear(left_eye, right_eye)

    # EAR kiri = 0.5
    # EAR kanan = 0.4
    # Rata-rata = 0.45
    assert avg_ear == pytest.approx(0.45, abs=1e-6)


def test_calculate_perclos():
    """
    Menguji PERCLOS.

    1 berarti mata tertutup.
    0 berarti mata terbuka.

    Dari 10 data, ada 3 data tertutup.
    PERCLOS = 3 / 10 = 0.3
    """
    closed_values = [0, 0, 1, 0, 1, 0, 0, 1, 0, 0]

    perclos = calculate_perclos(closed_values)

    assert perclos == pytest.approx(0.3, abs=1e-6)


def test_calculate_perclos_empty_data():
    """
    Jika data kosong, PERCLOS harus 0 agar sistem tidak error.
    """
    assert calculate_perclos([]) == 0.0


def test_calculate_blink_rate():
    """
    Menguji blink rate.

    Jika dalam 120 detik terdapat 30 kedipan:
    blink rate = 30 / 120 * 60 = 15 kedipan/menit.
    """
    blink_rate = calculate_blink_rate(blink_count=30, elapsed_seconds=120)

    assert blink_rate == pytest.approx(15.0, abs=1e-6)


def test_clamp_value():
    """
    Menguji fungsi clamp agar nilai tidak keluar dari batas minimum dan maksimum.
    """
    assert clamp(50, 0, 100) == 50
    assert clamp(-10, 0, 100) == 0
    assert clamp(120, 0, 100) == 100


def test_normalize_score():
    """
    Menguji normalisasi nilai ke rentang 0 sampai 1.
    """
    assert normalize_score(50, 0, 100) == pytest.approx(0.5, abs=1e-6)
    assert normalize_score(-10, 0, 100) == 0.0
    assert normalize_score(120, 0, 100) == 1.0


def test_remove_outliers_iqr():
    """
    Menguji pembersihan outlier saat kalibrasi EAR.

    Nilai 10.0 adalah outlier dan harus dibuang.
    """
    values = [0.25, 0.26, 0.27, 0.28, 10.0]

    clean_values = remove_outliers_iqr(values)

    assert 10.0 not in clean_values
    assert len(clean_values) == 4