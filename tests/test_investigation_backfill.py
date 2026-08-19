"""Bổ sung bằng chứng bắt buộc trước khi tác tử được viết.

Đo trên 227 phiên điều tra thật: 159 phiên trượt phản biện, và ``GetGraphEvidence``
bị đòi **279 lần** — áp đảo mọi nguyên nhân khác. Nguyên nhân không phải mô hình
chấm sai (``INVALID_SCORE`` xuất hiện **0 lần**) mà là tác tử viết trước khi gọi
đủ công cụ, rồi tự khai là thiếu dữ liệu.

Bộ test khoá hành vi bổ sung tất định: quy trình tự gọi công cụ còn thiếu, nên
tác tử không có cơ hội bỏ qua.

Từ bản tiếng Việt của tầng diễn giải, hai công cụ ``GetAccountBehavior`` và
``GetTransactions`` được gọi cho **mọi** cảnh báo, không phụ thuộc detector: câu
tóm tắt phải nói được tài khoản nhận bao nhiêu, từ ngày nào, chuyển đi đâu — và
không có hai công cụ ấy thì không có số để nói.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.investigation.schemas import EvidenceType  # noqa: E402
from src.investigation.workflow import InvestigationWorkflow  # noqa: E402


class _Evidence:
    def __init__(self, evidence_type: EvidenceType, evidence_id: str = "EV-1", *, window_days: int = 30) -> None:
        self.type = evidence_type
        self.evidence_id = evidence_id
        # ``window_days`` để bước bổ sung phân biệt cửa sổ hành vi đủ rộng với
        # cửa sổ hẹp: có bằng chứng chưa đủ, nó phải phủ được tập giao dịch.
        self.payload = {"observed": {"window_days": window_days}}


class _Execution:
    status = "SUCCEEDED"

    def __init__(self, evidence_id: str = "EV-NEW") -> None:
        self.evidence = _Evidence(EvidenceType.GRAPH_PATTERN, evidence_id)
        self.result = {"ok": True}


class _Repo:
    def __init__(self, existing: list[EvidenceType]) -> None:
        self.existing = [_Evidence(t) for t in existing]
        self.traces: list[dict[str, Any]] = []
        self.tool_calls: list[str] = []

    def list_evidence(self, _investigation_id: str) -> list[_Evidence]:
        return self.existing

    def add_trace(self, _investigation_id: str, **kwargs: Any) -> str:
        self.traces.append(kwargs)
        return "TR-1"

    def record_tool_call(self, _iid: str, _run: str, tool: str, *_a: Any, **_k: Any) -> str:
        self.tool_calls.append(tool)
        return "TC-1"


def _workflow(repo: _Repo) -> InvestigationWorkflow:
    workflow = InvestigationWorkflow.__new__(InvestigationWorkflow)
    workflow.repository = repo  # type: ignore[attr-defined]
    return workflow


def _run(monkeypatch: pytest.MonkeyPatch, repo: _Repo, alert: dict[str, Any], *, fail: bool = False) -> int:
    called: list[tuple[str, dict[str, Any]]] = []

    def fake_timed_execute(_tools: Any, tool: str, arguments: dict[str, Any]):  # noqa: ANN202
        called.append((tool, arguments))
        if fail:
            raise RuntimeError("tool exploded")
        from datetime import UTC, datetime

        return _Execution(), datetime.now(UTC), 12

    monkeypatch.setattr("src.investigation.workflow.timed_execute", fake_timed_execute)
    count = _workflow(repo)._backfill_required_evidence(
        investigation_id="INV-1", alert=alert, tools=object(), agent_run="RUN-1", tool_count=5
    )
    repo.called = called  # type: ignore[attr-defined]
    return count


GRAPH_ALERT = {"alert_id": "ALT-1", "account_key": "1:A", "detector": "graph"}
ML_ALERT = {"alert_id": "ALT-2", "account_key": "1:B", "detector": "ml"}
RULE_ALERT = {"alert_id": "ALT-3", "account_key": "1:C", "detector": "rule"}


# Hai lời gọi nền, có ở mọi cảnh báo. Viết ra thành hằng số để mỗi test chỉ còn
# khẳng định đúng phần RIÊNG của detector mình đang xét.
def _always(account_key: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("GetAccountBehavior", {"account_key": account_key, "window": "30d"}),
        ("GetTransactions", {"account_key": account_key}),
    ]


def test_graph_alert_without_graph_evidence_triggers_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo([EvidenceType.RISK_BREAKDOWN])
    count = _run(monkeypatch, repo, GRAPH_ALERT)
    assert repo.called == [*_always("1:A"), ("GetGraphEvidence", {"alert_id": "ALT-1"})]  # type: ignore[attr-defined]
    assert count == 8


def test_backfill_is_skipped_when_evidence_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kiểm bằng bằng chứng đã có, không bằng bộ đếm lời gọi."""
    repo = _Repo([EvidenceType.GRAPH_PATTERN, EvidenceType.BEHAVIOR_FEATURE, EvidenceType.TRANSACTION])
    count = _run(monkeypatch, repo, GRAPH_ALERT)
    assert repo.called == []  # type: ignore[attr-defined]
    assert count == 5


def test_narrow_behavior_window_is_widened_even_though_evidence_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cửa sổ 7 ngày có sẵn KHÔNG được tính là đã đủ.

    Đây là nguồn mâu thuẫn đã quan sát trên hồ sơ thật: tác tử tự gọi cửa sổ mặc
    định 7 ngày, bước bổ sung thấy "đã có BEHAVIOR_FEATURE" rồi bỏ qua, và câu
    tóm tắt viết "chuyển đi 0,00 Euro tới 0 đối tác" ngay phía trên hai dòng dữ
    kiện ghi rõ hai lần chuyển 30.101,17 Euro nằm ngoài bảy ngày ấy.
    """
    repo = _Repo([])
    repo.existing = [
        _Evidence(EvidenceType.BEHAVIOR_FEATURE, window_days=7),
        _Evidence(EvidenceType.TRANSACTION),
        _Evidence(EvidenceType.GRAPH_PATTERN),
    ]
    _run(monkeypatch, repo, GRAPH_ALERT)
    assert repo.called == [  # type: ignore[attr-defined]
        ("GetAccountBehavior", {"account_key": "1:A", "window": "30d"}),
    ]


def test_ml_alert_backfills_anomaly_explanation_with_account_key(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo([])
    _run(monkeypatch, repo, ML_ALERT)
    assert repo.called == [  # type: ignore[attr-defined]
        *_always("1:B"),
        ("GetAnomalyExplanation", {"alert_id": "ALT-2", "account_key": "1:B"}),
    ]


def test_rule_alert_needs_no_detector_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cảnh báo luật không có bằng chứng riêng của detector nào để bổ sung.

    Nhưng hai lời gọi nền vẫn chạy: hồ sơ nào cũng phải kể được dòng tiền, kể cả
    hồ sơ do luật sinh ra.
    """
    repo = _Repo([])
    count = _run(monkeypatch, repo, RULE_ALERT)
    assert repo.called == _always("1:C")  # type: ignore[attr-defined]
    assert count == 7


def test_always_required_are_skipped_when_already_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hai lời gọi nền là bắt buộc, không phải vô điều kiện.

    Tác tử đã tự gọi rồi thì quy trình không gọi lại — ngân sách công cụ hữu hạn.
    """
    repo = _Repo([EvidenceType.BEHAVIOR_FEATURE, EvidenceType.TRANSACTION])
    count = _run(monkeypatch, repo, RULE_ALERT)
    assert repo.called == []  # type: ignore[attr-defined]
    assert count == 5


def test_tool_failure_does_not_break_the_investigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bổ sung là để giúp, không phải để giấu: lỗi được ghi lại, phiên vẫn chạy tiếp."""
    repo = _Repo([])
    count = _run(monkeypatch, repo, GRAPH_ALERT, fail=True)
    assert count == 8
    assert any("thất bại" in str(t.get("rationale", "")) for t in repo.traces)


def test_backfill_is_traced_as_workflow_not_as_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dấu vết phải nói rõ ai gọi, để không ai tưởng tác tử đã tự chọn công cụ."""
    repo = _Repo([])
    _run(monkeypatch, repo, GRAPH_ALERT)
    assert {t["agent"] for t in repo.traces} == {"workflow"}
    assert repo.tool_calls == ["GetAccountBehavior", "GetTransactions", "GetGraphEvidence"]
