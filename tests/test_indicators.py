from statistics import mean, stdev

import pytest

from app.market.indicators import bollinger_bands


def test_first_19_sessions_are_empty_and_20th_has_value():
    closes = [float(i) for i in range(1, 41)]
    bands = bollinger_bands(closes)
    assert bands[:19] == [None] * 19
    assert bands[19] is not None


def test_uses_sample_standard_deviation():
    closes = [100, 102, 101, 99, 98, 103, 105, 104, 102, 101,
              100, 99, 97, 96, 98, 100, 102, 103, 104, 106.0]
    band = bollinger_bands(closes)[-1]
    assert band.middle == pytest.approx(mean(closes))
    assert band.upper == pytest.approx(mean(closes) + 2 * stdev(closes))
    assert band.lower == pytest.approx(mean(closes) - 2 * stdev(closes))
