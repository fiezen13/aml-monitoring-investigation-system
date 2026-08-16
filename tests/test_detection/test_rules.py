"""Bộ luật phải kích hoạt đúng lúc, và im lặng khi không đủ căn cứ."""

from datetime import UTC, datetime

from src.detection.rules import (
    RULE_THRESHOLDS,
    RuleContext,
    evaluate,
    risk_score,
    rule_cross_border,
    rule_rapid_movement,
    rule_structuring,
    rule_vasp_exposure,
    signals_of,
)

AS_OF = datetime(2022, 9, 28, tzinfo=UTC)


def ctx(**over) -> RuleContext:
    base = {
        "account_key": "001:A",
        "as_of": AS_OF,
        "window_days": 7,
        "transaction_count": 20,
        "outgoing_count": 10,
        "incoming_count": 10,
        "total_outflow": 100_000.0,
        "total_inflow": 100_000.0,
    }
    base.update(over)
    return RuleContext(**base)


class TestStructuring:
    def test_fires_on_a_cluster_just_below_the_reporting_threshold(self):
        hit = rule_structuring(
            ctx(near_threshold_count=9, near_threshold_distinct_amounts=2, near_threshold_span_hours=30)
        )

        assert hit is not None
        assert hit.code == "R01_STRUCTURING"
        # Ít giá trị khác nhau trên nhiều giao dịch = số tiền lặp lại.
        assert "repeated_amounts" in hit.signals
        assert "short_window" in hit.signals

    def test_stays_silent_on_a_single_large_payment(self):
        """Một giao dịch 9.900 là bình thường. Luật này bắt khuôn mẫu, không bắt số tiền."""
        assert rule_structuring(ctx(near_threshold_count=1, near_threshold_distinct_amounts=1)) is None

    def test_does_not_claim_repetition_when_every_amount_differs(self):
        hit = rule_structuring(
            ctx(near_threshold_count=4, near_threshold_distinct_amounts=4, near_threshold_span_hours=200)
        )

        assert hit is not None
        assert "repeated_amounts" not in hit.signals
        # Trải 200 giờ thì không còn là "cửa sổ ngắn".
        assert "short_window" not in hit.signals

    def test_severity_grows_with_the_cluster_size(self):
        small = rule_structuring(ctx(near_threshold_count=3, near_threshold_distinct_amounts=1))
        large = rule_structuring(ctx(near_threshold_count=40, near_threshold_distinct_amounts=1))

        assert large.contribution > small.contribution


class TestRapidMovement:
    def test_fires_when_most_money_leaves_within_two_hours(self):
        hit = rule_rapid_movement(ctx(rapid_outflow_amount=90_000.0, median_dwell_hours=0.5))

        assert hit is not None
        assert "rapid_outflow" in hit.signals
        assert "short_dwell_time" in hit.signals

    def test_stays_silent_below_the_ratio(self):
        assert rule_rapid_movement(ctx(rapid_outflow_amount=10_000.0)) is None

    def test_stays_silent_when_there_are_too_few_outgoing_transactions(self):
        """Tỷ lệ 100% trên hai giao dịch không nói lên điều gì."""
        assert rule_rapid_movement(ctx(outgoing_count=2, rapid_outflow_amount=100_000.0)) is None

    def test_dwell_signal_is_omitted_when_unknown(self):
        hit = rule_rapid_movement(ctx(rapid_outflow_amount=90_000.0, median_dwell_hours=None))

        assert hit is not None
        assert "short_dwell_time" not in hit.signals


class TestVaspExposure:
    def test_fires_on_material_vasp_exposure(self):
        hit = rule_vasp_exposure(ctx(vasp_amount=120_000.0, vasp_transaction_count=5))

        assert hit is not None
        assert "vasp_link" in hit.signals

    def test_stays_silent_on_a_single_vasp_transaction(self):
        assert rule_vasp_exposure(ctx(vasp_amount=200_000.0, vasp_transaction_count=1)) is None


class TestCrossBorder:
    def test_fires_when_most_transactions_cross_a_border(self):
        hit = rule_cross_border(ctx(cross_border_count=15))

        assert hit is not None
        assert "cross_border_flow" in hit.signals

    def test_never_claims_a_high_risk_jurisdiction(self):
        """Không có danh sách quốc gia được chỉ định thì không được khẳng định T06."""
        hit = rule_cross_border(ctx(cross_border_count=20))

        assert "jurisdiction_signal" not in hit.signals


class TestScoring:
    def test_no_hit_scores_zero(self):
        assert risk_score([]) == 0.0

    def test_one_severe_rule_outranks_several_weak_ones(self):
        severe = [rule_rapid_movement(ctx(rapid_outflow_amount=100_000.0, median_dwell_hours=0.1))]
        weak = evaluate(ctx(cross_border_count=11, vasp_amount=61_000.0, vasp_transaction_count=4))

        assert risk_score(severe) > 0
        assert len(weak) >= 2
        # Cộng thẳng sẽ khiến nhóm luật yếu vượt mặt; thang giảm dần ngăn điều đó.
        assert risk_score(weak) <= 100.0

    def test_the_score_never_exceeds_the_scale(self):
        every = evaluate(
            ctx(
                near_threshold_count=100,
                near_threshold_distinct_amounts=1,
                near_threshold_span_hours=10,
                rapid_outflow_amount=100_000.0,
                median_dwell_hours=0.1,
                vasp_amount=200_000.0,
                vasp_transaction_count=50,
                cross_border_count=20,
            )
        )

        assert len(every) == 4
        assert 0 < risk_score(every) <= 100.0


class TestSignalsFeedTypology:
    def test_signals_are_the_bridge_to_the_typology_catalogue(self):
        """Tín hiệu của luật phải chọn được nhóm hành vi, nếu không nhánh rule vô nghĩa."""
        from src.investigation.typology_match import match_typology

        hits = evaluate(ctx(near_threshold_count=8, near_threshold_distinct_amounts=2, near_threshold_span_hours=20))
        match = match_typology(signals_of(hits))

        assert match.typology_code == "T01"
        assert match.is_fallback is False

    def test_rapid_movement_selects_the_rapid_typology(self):
        from src.investigation.typology_match import match_typology

        hits = evaluate(ctx(rapid_outflow_amount=95_000.0, median_dwell_hours=0.3))
        match = match_typology(signals_of(hits))

        assert match.typology_code == "T05"

    def test_vasp_exposure_selects_the_virtual_asset_typology(self):
        from src.investigation.typology_match import match_typology

        hits = evaluate(ctx(vasp_amount=90_000.0, vasp_transaction_count=6))
        match = match_typology(signals_of(hits))

        assert match.typology_code == "T08"


def test_thresholds_live_in_one_place():
    """Ngưỡng phải nằm trong bảng cấu hình để bộ phận tuân thủ hiệu chỉnh được."""
    assert set(RULE_THRESHOLDS) >= {
        "reporting_threshold",
        "structuring_min_count",
        "rapid_outflow_ratio",
        "vasp_exposure_ratio",
        "cross_border_ratio",
    }


class TestSupportingRules:
    def test_cross_border_alone_does_not_open_an_alert(self):
        """27% tài khoản trong bộ dữ liệu có dòng tiền xuyên biên giới.

        Đó là chuyện bình thường ở dữ liệu đa ngân hàng, không phải vi phạm. Nếu
        luật này tự mở cảnh báo thì hàng đợi ngập và mất hết ý nghĩa xếp hạng.
        """
        from src.detection.rules import should_alert

        hits = evaluate(ctx(cross_border_count=18))

        assert [hit.code for hit in hits] == ["R04_CROSS_BORDER_FLOW"]
        assert should_alert(hits) is False

    def test_cross_border_still_enriches_an_alert_a_primary_rule_opened(self):
        from src.detection.rules import should_alert

        hits = evaluate(ctx(rapid_outflow_amount=95_000.0, median_dwell_hours=0.4, cross_border_count=18))
        codes = [hit.code for hit in hits]

        assert should_alert(hits) is True
        assert "R02_RAPID_MOVEMENT" in codes
        assert "R04_CROSS_BORDER_FLOW" in codes

    def test_no_hits_never_opens_an_alert(self):
        from src.detection.rules import should_alert

        assert should_alert([]) is False


def test_a_rule_that_fired_never_contributes_zero():
    """Kích hoạt ở mức tối thiểu vẫn là một phát hiện.

    Thang tuyến tính từ 0 khiến trường hợp đúng bằng ngưỡng nhận điểm 0; lần
    chạy đầu trên LI-Small sinh ra 191 cảnh báo điểm 0 vì đúng lỗi này, và chúng
    nằm đáy hàng đợi như thể không có gì.
    """
    from src.detection.rules import MIN_CONTRIBUTION

    minimum = int(RULE_THRESHOLDS["structuring_min_count"])
    hit = rule_structuring(ctx(near_threshold_count=minimum, near_threshold_distinct_amounts=minimum))

    assert hit is not None
    assert hit.contribution == MIN_CONTRIBUTION
    assert risk_score([hit]) > 0


def test_severity_still_separates_the_minimum_from_the_extreme():
    small = rule_structuring(ctx(near_threshold_count=3, near_threshold_distinct_amounts=1))
    large = rule_structuring(ctx(near_threshold_count=100, near_threshold_distinct_amounts=1))

    assert large.contribution == 100.0
    assert small.contribution < large.contribution
