"""Tests for MLIT transaction connector - station-level stats and trend computation."""

from app.connectors.mlit_transaction import (
    StationAreaStats,
    TransactionRecord,
    _compute_quarterly_prices,
    _compute_trend,
    _median,
    _parse_built_year,
    _period_to_sort_key,
    city_code_to_name,
    city_name_to_code,
    prefecture_name_to_code,
    station_stats_to_area_data,
)


# ---------------------------------------------------------------------------
# Helper: create sample transaction records
# ---------------------------------------------------------------------------


def _make_record(
    station: str = "塚口",
    price: int = 35_000_000,
    area: float = 70.0,
    period: str = "2024年第3四半期",
    built_year: int = 2015,
) -> TransactionRecord:
    return TransactionRecord(
        property_type="マンション等",
        prefecture="兵庫県",
        city="尼崎市",
        district="塚口本町",
        nearest_station=station,
        walking_minutes=5,
        trade_price=price,
        floor_area=area,
        built_year=built_year,
        layout="3LDK",
        trade_period=period,
        unit_price=int(price / area) if area > 0 else None,
    )


# ---------------------------------------------------------------------------
# Tests: parsing helpers
# ---------------------------------------------------------------------------


class TestParseBuiltYear:
    def test_western_year(self):
        assert _parse_built_year("2018年") == 2018

    def test_western_year_no_suffix(self):
        assert _parse_built_year("2020") == 2020

    def test_reiwa(self):
        assert _parse_built_year("令和5年") == 2023

    def test_heisei(self):
        assert _parse_built_year("平成30年") == 2018

    def test_showa(self):
        assert _parse_built_year("昭和60年") == 1985

    def test_none(self):
        assert _parse_built_year(None) is None

    def test_invalid(self):
        assert _parse_built_year("不明") is None


class TestPeriodToSortKey:
    def test_standard(self):
        assert _period_to_sort_key("2024年第3四半期") == "20243"

    def test_q1(self):
        assert _period_to_sort_key("2023年第1四半期") == "20231"


class TestMedian:
    def test_odd(self):
        assert _median([1, 3, 5]) == 3

    def test_even(self):
        assert _median([1, 3, 5, 7]) == 4

    def test_single(self):
        assert _median([42]) == 42


# ---------------------------------------------------------------------------
# Tests: city/prefecture code lookups
# ---------------------------------------------------------------------------


class TestCodeLookups:
    def test_prefecture_name_to_code(self):
        assert prefecture_name_to_code("兵庫県") == "28"
        assert prefecture_name_to_code("東京都") == "13"
        assert prefecture_name_to_code("不明県") == ""

    def test_city_name_to_code(self):
        assert city_name_to_code("尼崎市") == "28202"
        assert city_name_to_code("西宮市") == "28204"

    def test_city_code_to_name(self):
        assert city_code_to_name("28202") == "尼崎市"
        assert city_code_to_name("99999") == ""

    def test_city_name_fuzzy(self):
        # Partial match should work
        code = city_name_to_code("尼崎")
        assert code == "28202"


# ---------------------------------------------------------------------------
# Tests: quarterly price computation
# ---------------------------------------------------------------------------


class TestComputeQuarterlyPrices:
    def test_basic(self):
        records = [
            _make_record(price=35_000_000, area=70, period="2023年第1四半期"),
            _make_record(price=36_000_000, area=72, period="2023年第1四半期"),
            _make_record(price=38_000_000, area=70, period="2024年第1四半期"),
        ]
        result = _compute_quarterly_prices(records)
        assert len(result) == 2
        assert result[0]["sort_key"] == "20231"
        assert result[1]["sort_key"] == "20241"
        # 2023Q1: 500000 and 500000 → avg 500000
        assert result[0]["avg_unit_price"] == 500_000
        assert result[0]["count"] == 2

    def test_empty(self):
        assert _compute_quarterly_prices([]) == []

    def test_sorted_chronologically(self):
        records = [
            _make_record(period="2024年第3四半期"),
            _make_record(period="2023年第1四半期"),
            _make_record(period="2024年第1四半期"),
        ]
        result = _compute_quarterly_prices(records)
        sort_keys = [r["sort_key"] for r in result]
        assert sort_keys == sorted(sort_keys)


# ---------------------------------------------------------------------------
# Tests: trend computation
# ---------------------------------------------------------------------------


class TestComputeTrend:
    def test_rising(self):
        quarterly = [
            {"avg_unit_price": 400_000, "count": 10},
            {"avg_unit_price": 410_000, "count": 10},
            {"avg_unit_price": 430_000, "count": 10},
            {"avg_unit_price": 450_000, "count": 10},
        ]
        label, pct = _compute_trend(quarterly)
        assert label in ("上昇", "やや上昇")
        assert pct > 0

    def test_stable(self):
        quarterly = [
            {"avg_unit_price": 400_000, "count": 10},
            {"avg_unit_price": 401_000, "count": 10},
            {"avg_unit_price": 399_000, "count": 10},
            {"avg_unit_price": 400_000, "count": 10},
        ]
        label, pct = _compute_trend(quarterly)
        assert label == "横ばい"
        assert abs(pct) < 2

    def test_declining(self):
        quarterly = [
            {"avg_unit_price": 500_000, "count": 10},
            {"avg_unit_price": 490_000, "count": 10},
            {"avg_unit_price": 460_000, "count": 10},
            {"avg_unit_price": 450_000, "count": 10},
        ]
        label, pct = _compute_trend(quarterly)
        assert label in ("下落", "やや下落")
        assert pct < 0

    def test_insufficient_data(self):
        quarterly = [{"avg_unit_price": 400_000, "count": 10}]
        label, pct = _compute_trend(quarterly)
        assert label == "データ不足"


# ---------------------------------------------------------------------------
# Tests: station_stats_to_area_data conversion
# ---------------------------------------------------------------------------


class TestStationStatsToAreaData:
    def test_conversion(self):
        stats = StationAreaStats(
            area_name="塚口駅周辺",
            prefecture="兵庫県",
            avg_unit_price_sqm=420_000,
            median_unit_price_sqm=410_000,
            avg_price_70sqm=29_400_000,
            avg_rent_per_sqm=None,
            avg_gross_yield=None,
            transaction_count=50,
            price_trend="上昇",
            price_trend_pct=5.2,
            quarterly_prices=[],
            source="MLIT API",
            period_range="20221-20254",
        )
        data = station_stats_to_area_data(stats)
        assert data["area_name"] == "塚口駅周辺"
        assert data["avg_unit_price_sqm"] == 420_000
        assert data["data_quality"] == "MLIT実取引データ"
        assert data["avg_price_70sqm"] == 29_400_000
