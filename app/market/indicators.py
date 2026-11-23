"""Bollinger Bands dari Close: SMA 20 sesi dan +/-2 standar deviasi sampel."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence

BB_WINDOW = 20
BB_STD_MULTIPLIER = 2.0


@dataclass(frozen=True)
class Band:
    upper: float
    middle: float
    lower: float


def bollinger_bands(
    closes: Sequence[float],
    window: int = BB_WINDOW,
    multiplier: float = BB_STD_MULTIPLIER,
) -> list[Band | None]:
    """Satu nilai per Close. Sesi sebelum jendela penuh bernilai None.

    Standar deviasi memakai pembagi n - 1 (sampel), sesuai requirement R-03.
    """
    if window < 2:
        raise ValueError("window minimal 2 untuk standar deviasi sampel")

    result: list[Band | None] = []
    for index in range(len(closes)):
        if index + 1 < window:
            result.append(None)
            continue
        chunk = closes[index + 1 - window : index + 1]
        mean = sum(chunk) / window
        variance = sum((value - mean) ** 2 for value in chunk) / (window - 1)
        spread = multiplier * sqrt(variance)
        result.append(Band(upper=mean + spread, middle=mean, lower=mean - spread))
    return result
