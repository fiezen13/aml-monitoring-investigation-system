"""Chuẩn báo cáo benchmark dùng chung cho mọi nhánh phát hiện."""

from .standard import (
    CANONICAL_BUDGETS,
    SCHEMA_VERSION,
    build_report,
    metrics_at_threshold,
    operating_points,
    validate_report,
)

__all__ = [
    "CANONICAL_BUDGETS",
    "SCHEMA_VERSION",
    "build_report",
    "metrics_at_threshold",
    "operating_points",
    "validate_report",
]
