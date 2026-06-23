"""Tests for the 塚口 walk-distance qualification rule."""

from app.services.tsukaguchi_filter import (
    evaluate_access,
    parse_tsukaguchi_access,
)


class TestParseAccess:
    def test_hankyu_single(self):
        a = parse_tsukaguchi_access("阪急神戸線「塚口」徒歩8分")
        assert a.hankyu == 8
        assert a.jr is None
        assert a.unknown is None

    def test_jr_single(self):
        a = parse_tsukaguchi_access("JR宝塚線「塚口」徒歩6分")
        assert a.jr == 6
        assert a.hankyu is None

    def test_both_stations_slash_separated(self):
        a = parse_tsukaguchi_access("阪急神戸線「塚口」徒歩12分／JR宝塚線「塚口」徒歩14分")
        assert a.hankyu == 12
        assert a.jr == 14

    def test_both_stations_space_separated(self):
        a = parse_tsukaguchi_access("阪急神戸線「塚口」徒歩9分 JR福知山線「塚口」徒歩13分")
        assert a.hankyu == 9
        assert a.jr == 13

    def test_homes_style_no_brackets(self):
        a = parse_tsukaguchi_access("阪急神戸線 塚口駅 徒歩5分")
        assert a.hankyu == 5

    def test_unknown_operator(self):
        a = parse_tsukaguchi_access("塚口駅 徒歩9分")
        assert a.unknown == 9
        assert a.hankyu is None
        assert a.jr is None

    def test_other_station_ignored(self):
        a = parse_tsukaguchi_access("阪急神戸線「武庫之荘」徒歩4分")
        assert a.hankyu is None and a.jr is None and a.unknown is None

    def test_takes_minimum_per_operator(self):
        a = parse_tsukaguchi_access("阪急伊丹線「塚口」徒歩11分／阪急神戸線「塚口」徒歩7分")
        assert a.hankyu == 7


class TestEvaluateRuleA:
    """阪急塚口 within 10 minutes."""

    def test_hankyu_within_10_qualifies(self):
        r = evaluate_access("阪急神戸線「塚口」徒歩8分")
        assert r.qualifies
        assert "阪急塚口" in r.reason

    def test_hankyu_exactly_10_qualifies(self):
        assert evaluate_access("阪急神戸線「塚口」徒歩10分").qualifies

    def test_hankyu_over_10_alone_fails(self):
        assert not evaluate_access("阪急神戸線「塚口」徒歩12分").qualifies


class TestEvaluateRuleB:
    """Both 阪急塚口 and JR塚口 within 15 minutes."""

    def test_both_within_15_qualifies(self):
        r = evaluate_access("阪急神戸線「塚口」徒歩12分／JR宝塚線「塚口」徒歩14分")
        assert r.qualifies
        assert "両駅" in r.reason

    def test_both_boundary_15_qualifies(self):
        assert evaluate_access("阪急神戸線「塚口」徒歩15分／JR宝塚線「塚口」徒歩15分").qualifies

    def test_one_over_15_fails(self):
        assert not evaluate_access(
            "阪急神戸線「塚口」徒歩12分／JR宝塚線「塚口」徒歩16分"
        ).qualifies

    def test_jr_alone_within_10_fails(self):
        # JR 6 min but no 阪急 → neither rule satisfied.
        assert not evaluate_access("JR宝塚線「塚口」徒歩6分").qualifies


class TestUnknownOperator:
    def test_unknown_within_10_assumed_hankyu(self):
        r = evaluate_access("塚口駅 徒歩9分")
        assert r.qualifies
        assert "推定" in r.reason

    def test_unknown_disabled(self):
        r = evaluate_access("塚口駅 徒歩9分", assume_unknown_is_hankyu=False)
        assert not r.qualifies

    def test_unknown_over_10_fails(self):
        assert not evaluate_access("塚口駅 徒歩12分").qualifies


class TestEvaluateMisc:
    def test_empty(self):
        assert not evaluate_access("").qualifies

    def test_other_station(self):
        assert not evaluate_access("阪急神戸線「武庫之荘」徒歩4分").qualifies
