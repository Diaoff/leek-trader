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


def test_bias_calculates_multi_period_values() -> None:
    closes = [10, 11, 12, 13, 14, 15]

    result = IndicatorService.bias(closes, short_period=3, medium_period=4, long_period=6)

    assert result.insufficient is False
    assert round(result.bias1 or 0, 6) == 7.142857
    assert round(result.bias2 or 0, 6) == 11.111111
    assert round(result.bias3 or 0, 6) == 20.0
    assert result.series[1]["bias1"] is None


def test_williams_r_calculates_dual_period_values() -> None:
    highs = [10, 11, 12, 13, 14, 15]
    lows = [8, 8, 9, 10, 11, 12]
    closes = [9, 10, 11, 12, 13, 14]

    result = IndicatorService.williams_r(closes, highs, lows, period=5, short_period=3)

    assert result.insufficient is False
    assert round(result.wr1 or 0, 6) == 14.285714
    assert round(result.wr2 or 0, 6) == 20.0
    assert result.series[3]["wr1"] is None


def test_cci_calculates_latest_value() -> None:
    highs = [10, 11, 12, 13, 14]
    lows = [8, 8, 9, 10, 11]
    closes = [9, 10, 11, 12, 13]

    result = IndicatorService.cci(closes, highs, lows, period=3)

    assert result.insufficient is False
    assert round(result.value or 0, 6) == 100.0


def test_bbi_calculates_latest_value() -> None:
    closes = [10, 11, 12, 13, 14, 15]

    result = IndicatorService.bbi(closes, period1=2, period2=3, period3=4, period4=6)

    assert result.insufficient is False
    assert result.value == 13.625
    assert result.series[4] is None


def test_formula_compatibility_helpers() -> None:
    values = [1, 2, 3, 2, 5]

    assert IndicatorService.ref(values, 2) == [None, None, 1.0, 2.0, 3.0]
    assert IndicatorService.hhv(values, 3) == [None, None, 3.0, 3.0, 5.0]
    assert IndicatorService.llv(values, 3) == [None, None, 1.0, 2.0, 2.0]
    assert IndicatorService.cross([1, 2, 1, 4], [2, 2, 2, 3]) == [False, False, False, True]
    assert IndicatorService.count([True, False, True, True], 3) == [None, None, 2, 2]
    assert IndicatorService.every([True, True, False, True], 2) == [None, True, False, False]
    assert IndicatorService.sma([1, 2, 3], 3, 1) == [1.0, 1.3333333333333333, 1.8888888888888886]
