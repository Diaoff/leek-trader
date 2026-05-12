from app.indicators.service import IndicatorService


def test_rsi_handles_short_series() -> None:
    result = IndicatorService.rsi([1, 2, 3], period=14)

    assert result.value is None
    assert result.insufficient is True
    assert result.series == [None, None, None]


def test_rsi_calculates_latest_value() -> None:
    values = [44, 44.15, 43.9, 44.35, 44.6, 45, 44.8, 45.2, 45.8, 46.1, 45.9, 46.4, 46.8, 47.1, 47.4, 47.0]

    result = IndicatorService.rsi(values, period=14)

    assert result.value is not None
    assert 0 <= result.value <= 100
    assert result.insufficient is False


def test_boll_calculates_bands() -> None:
    result = IndicatorService.boll([10, 11, 12, 13, 14], period=5, stddev_multiplier=2)

    assert result.middle == 12
    assert result.upper is not None
    assert result.lower is not None
    assert result.upper > result.middle > result.lower


def test_kdj_calculates_latest_values() -> None:
    highs = [10, 11, 12, 13, 14, 15, 16, 17, 18]
    lows = [8, 8.5, 9, 10, 11, 12, 13, 14, 15]
    closes = [9, 10, 11, 12, 13, 14, 15, 16, 17]

    result = IndicatorService.kdj(highs, lows, closes, period=9)

    assert result.k is not None
    assert result.d is not None
    assert result.j is not None


def test_atr_and_obv_are_stable() -> None:
    highs = [11, 12, 13, 14, 15]
    lows = [9, 10, 11, 12, 13]
    closes = [10, 11, 10, 13, 14]
    volumes = [100, 120, 80, 200, 180]

    atr = IndicatorService.atr(highs, lows, closes, period=3)
    obv = IndicatorService.obv(closes, volumes)

    assert atr.value is not None
    assert obv.value == 420
