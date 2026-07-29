"""Dữ liệu mẫu phải tái lập được (ND5).

"Không tái lập được thì không so sánh được giữa các lần chạy, và mọi cải
thiện đo được đều đáng ngờ." Bài kiểm thử này không cần cơ sở dữ liệu: nó
dựng tập dữ liệu trong bộ nhớ và so vân tay.
"""

import pytest

from scripts.seed_data import ANCHOR, SeedBuilder

SEED = 20260728


@pytest.fixture(scope="module")
def built() -> SeedBuilder:
    return SeedBuilder(seed=SEED, customers=48, days=90).build()


def test_same_seed_gives_same_data():
    first = SeedBuilder(seed=SEED, customers=48, days=90).build()
    second = SeedBuilder(seed=SEED, customers=48, days=90).build()
    assert first.fingerprint() == second.fingerprint()


def test_different_seed_gives_different_data(built):
    other = SeedBuilder(seed=SEED + 1, customers=48, days=90).build()
    assert other.fingerprint() != built.fingerprint()


def test_timestamps_do_not_depend_on_wall_clock(built):
    """Mốc thời gian neo vào hằng số, không vào đồng hồ máy chạy script."""
    assert max(t["occurred_at"] for t in built.transactions) <= ANCHOR


def test_time_based_split_has_no_leakage(built):
    """ND2 — chia theo thời gian, không chia ngẫu nhiên.

    Không giao dịch nào của tập kiểm thử được sớm hơn giao dịch muộn nhất của
    tập huấn luyện; ngược lại là rò rỉ thông tin tương lai vào quá khứ.
    """
    latest_train = max(t["occurred_at"] for t in built.transactions if t["dataset_split"] == "train")
    earliest_test = min(t["occurred_at"] for t in built.transactions if t["dataset_split"] == "test")
    assert earliest_test > latest_train


def test_every_alert_has_at_least_three_factors(built):
    """NT7 — mọi cảnh báo phải trả về tối thiểu ba yếu tố đóng góp có giá trị số."""
    per_alert: dict[str, int] = {}
    for reason in built.alert_reasons:
        per_alert[reason["alert_id"]] = per_alert.get(reason["alert_id"], 0) + 1

    assert per_alert, "Không sinh được cảnh báo nào"
    thin = {alert_id: n for alert_id, n in per_alert.items() if n < 3}
    assert not thin, f"Cảnh báo có ít hơn ba yếu tố: {thin}"
    assert all(isinstance(r["contribution"], (int, float)) for r in built.alert_reasons)


def test_every_statement_cites_evidence(built):
    """NT1 — không có câu khẳng định nào đứng một mình."""
    cited = {link["statement_id"] for link in built.statement_evidence}
    uncited = [s["statement_id"] for s in built.sar_statements if s["statement_id"] not in cited]
    assert not uncited, f"Câu không tham chiếu bằng chứng: {uncited}"


def test_no_self_loops_in_transaction_graph(built):
    """Cạnh tự trỏ tạo chu trình không có thật khi phân tích đồ thị."""
    assert not [t for t in built.transactions if t["from_account_key"] == t["to_account_key"]]


def test_account_key_includes_bank_code(built):
    """DAT-001 mục 4.1 — lỗi im lặng: không ghép mã ngân hàng thì hai tài khoản
    khác nhau ở hai ngân hàng bị coi là một."""
    for account in built.accounts:
        assert account["account_key"] == f"{account['bank_code']}:{account['account_number']}"
    assert len({a["account_key"] for a in built.accounts}) == len(built.accounts)


def test_watchlist_keeps_three_versions(built):
    """DAT-001 mục 7.1 — giữ tối thiểu ba phiên bản để diễn tập kiểm toán."""
    assert len(built.watchlist_versions) >= 3


def test_near_miss_group_exists(built):
    """DAT-001 mục 6 — không có nhóm gần giống thì không đo được khớp sai."""
    kinds = {m["match_type"] for m in built.watchlist_matches}
    assert "near_miss" in kinds
    assert "exact" in kinds


def test_profile_mismatch_is_independent_of_laundering(built):
    """T10 độc lập với nhãn rửa tiền: lệch hồ sơ là dấu hiệu cần điều tra,
    không phải bằng chứng rửa tiền (DAT-001 mục 5.4)."""
    laundering_tx = set(built.laundering_tx)
    mismatch_accounts = {row["account_key"] for row in built.profile_mismatch}
    laundering_accounts = {t["from_account_key"] for t in built.transactions if t["transaction_id"] in laundering_tx}
    assert mismatch_accounts, "Không tiêm lệch hồ sơ cho tài khoản nào"
    assert mismatch_accounts - laundering_accounts, (
        "Mọi tài khoản lệch hồ sơ đều trùng nhãn rửa tiền — mất hết nhóm dương tính giả hợp pháp"
    )


def test_planted_typologies_are_all_present(built):
    codes = {code for _, code in built.typology_tx}
    assert {"T01", "T02", "T03", "T04", "T05", "T10"} <= codes


def test_structuring_amounts_sit_below_threshold(built):
    """T01 — từng giao dịch hợp lệ, chỉ tổng cộng dồn mới vượt ngưỡng."""
    from scripts.seed_data import REPORTING_THRESHOLD

    t01_ids = {tx for tx, code in built.typology_tx if code == "T01"}
    amounts = [t["amount"] for t in built.transactions if t["transaction_id"] in t01_ids]
    assert amounts
    assert all(a < REPORTING_THRESHOLD for a in amounts)
    assert sum(amounts) > REPORTING_THRESHOLD
