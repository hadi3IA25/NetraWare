from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence, Tuple, List


Point = Tuple[float, float]

# 6 titik landmark mata untuk perhitungan EAR.
# Urutan: p1, p2, p3, p4, p5, p6
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]


def euclidean_distance(p1: Point, p2: Point) -> float:
    """
    Menghitung jarak Euclidean antara dua titik.
    """
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def calculate_ear(eye_points: Sequence[Point]) -> float:
    """
    Menghitung Eye Aspect Ratio (EAR).

    EAR digunakan untuk memperkirakan kondisi mata terbuka atau tertutup.

    Format titik:
    p1 = sudut horizontal pertama
    p2 = titik atas pertama
    p3 = titik atas kedua
    p4 = sudut horizontal kedua
    p5 = titik bawah kedua
    p6 = titik bawah pertama
    """
    if len(eye_points) != 6:
        raise ValueError("Perhitungan EAR membutuhkan tepat 6 titik landmark mata.")

    p1, p2, p3, p4, p5, p6 = eye_points

    vertical_1 = euclidean_distance(p2, p6)
    vertical_2 = euclidean_distance(p3, p5)
    horizontal = euclidean_distance(p1, p4)

    if horizontal <= 0:
        return 0.0

    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return float(ear)


def calculate_average_ear(left_eye_points: Sequence[Point], right_eye_points: Sequence[Point]) -> float:
    """
    Menghitung rata-rata EAR dari mata kiri dan mata kanan.
    """
    left_ear = calculate_ear(left_eye_points)
    right_ear = calculate_ear(right_eye_points)
    return (left_ear + right_ear) / 2.0


def calculate_perclos(closed_values: Iterable[int]) -> float:
    """
    Menghitung PERCLOS.

    PERCLOS = jumlah kondisi mata tertutup / seluruh sampel dalam periode tertentu.

    Nilai:
    0.0 = mata tidak pernah tertutup pada window tersebut
    1.0 = mata selalu tertutup pada window tersebut
    """
    values = list(closed_values)

    if not values:
        return 0.0

    closed_count = sum(1 for value in values if value == 1)
    return closed_count / len(values)


def calculate_blink_rate(blink_count: int, elapsed_seconds: float) -> float:
    """
    Menghitung jumlah kedipan per menit.
    """
    if elapsed_seconds <= 0:
        return 0.0

    return (blink_count / elapsed_seconds) * 60.0


def safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    """
    Menghitung rata-rata dengan aman.
    """
    clean_values = [float(v) for v in values if v is not None]

    if not clean_values:
        return default

    return statistics.mean(clean_values)


def percentile(values: Sequence[float], percent: float) -> float:
    """
    Menghitung persentil sederhana tanpa library tambahan.
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * percent / 100
    lower = math.floor(index)
    upper = math.ceil(index)

    if lower == upper:
        return sorted_values[int(index)]

    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]

    return lower_value + (upper_value - lower_value) * (index - lower)


def remove_outliers_iqr(values: Sequence[float]) -> List[float]:
    """
    Menghapus outlier menggunakan metode IQR.
    Cocok digunakan saat kalibrasi EAR agar nilai ekstrem tidak mengganggu baseline.
    """
    if len(values) < 4:
        return list(values)

    q1 = percentile(values, 25)
    q3 = percentile(values, 75)
    iqr = q3 - q1

    if iqr <= 0:
        return list(values)

    lower_bound = q1 - (1.5 * iqr)
    upper_bound = q3 + (1.5 * iqr)

    return [value for value in values if lower_bound <= value <= upper_bound]


def clamp(value: float, minimum: float, maximum: float) -> float:
    """
    Membatasi nilai agar berada di antara minimum dan maximum.
    """
    return max(minimum, min(value, maximum))


def normalize_score(value: float, minimum: float, maximum: float) -> float:
    """
    Mengubah nilai menjadi rentang 0 sampai 1.
    """
    if maximum <= minimum:
        return 0.0

    normalized = (value - minimum) / (maximum - minimum)
    return clamp(normalized, 0.0, 1.0)

