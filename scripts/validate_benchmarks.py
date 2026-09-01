#!/usr/bin/env python3
"""Quét ``reports/`` và từ chối báo cáo benchmark sai chuẩn.

    python scripts/validate_benchmarks.py            # kiểm, in tóm tắt
    python scripts/validate_benchmarks.py --strict   # báo cáo cũ cũng tính là lỗi

Gọi từ ``ci/test.sh``. Không có chốt này thì chuẩn chỉ là một tài liệu, và tài
liệu không ngăn được file thứ hai mươi ra đời với đơn vị đo thứ năm.

Báo cáo cũ (không mang ``fin07.benchmark.v1``) được liệt kê riêng chứ **không**
bị xoá: chúng vẫn là dấu vết của những gì đã chạy. Chỉ có điều chúng không được
trích dẫn — xem ``reports/README.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmark.standard import SCHEMA_VERSION, validate_report  # noqa: E402

#: File JSON trong reports/ không phải báo cáo benchmark — bỏ qua, đừng bắt lỗi.
NOT_BENCHMARKS = ("manifest", "preflight", "coverage", "catalog")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--strict", action="store_true", help="Coi báo cáo cũ là lỗi")
    parser.add_argument("--max-bytes", type=int, default=8_000_000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    conforming: list[Path] = []
    legacy: list[Path] = []
    failures: list[tuple[Path, list[str]]] = []

    for path in sorted(args.reports_dir.rglob("*.json")):
        if path.stat().st_size > args.max_bytes:
            continue
        if any(token in path.name for token in NOT_BENCHMARKS):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append((path, [f"không đọc được: {exc}"]))
            continue
        if not isinstance(payload, dict):
            continue

        if payload.get("schema_version") == SCHEMA_VERSION:
            problems = validate_report(payload)
            if problems:
                failures.append((path, problems))
            else:
                conforming.append(path)
        else:
            legacy.append(path)

    rel = lambda p: p.relative_to(ROOT)  # noqa: E731
    print(f"Đúng chuẩn {SCHEMA_VERSION}: {len(conforming)}")
    for path in conforming:
        print(f"  ✓ {rel(path)}")
    print(f"\nBáo cáo cũ, KHÔNG được trích dẫn: {len(legacy)}")
    for path in legacy:
        print(f"  · {rel(path)}")
    if failures:
        print(f"\nSAI CHUẨN: {len(failures)}")
        for path, problems in failures:
            print(f"  ✗ {rel(path)}")
            for problem in problems:
                print(f"      {problem}")

    if failures:
        return 1
    if args.strict and legacy:
        print("\n--strict: còn báo cáo cũ chưa chuyển đổi", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
