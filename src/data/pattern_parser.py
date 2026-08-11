"""Parse IBM AML Patterns.txt BEGIN/END blocks into IbmPatternInstance records."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.data.schemas import make_account_key
from src.data.typology_schema import (
    IbmPatternInstance,
    ParseStatus,
    canonicalize_pattern_type,
)

BEGIN_RE = re.compile(
    r"^BEGIN LAUNDERING ATTEMPT - ([A-Za-z0-9_\-]+)(?::\s*(.*))?$"
)
END_RE = re.compile(r"^END LAUNDERING ATTEMPT - ([A-Za-z0-9_\-]+)\s*$")

PARSER_VERSION = "v1.0"


class UnsupportedPatternFormatError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_instance_id(
    source_checksum: str, start_line: int, end_line: int, pattern_type: str
) -> str:
    payload = f"{source_checksum}|{start_line}|{end_line}|{pattern_type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _accounts_from_tx_lines(tx_lines: list[str]) -> list[dict[str, str]]:
    """Extract unique account refs from CSV-like pattern transaction lines."""
    seen: dict[str, dict[str, str]] = {}
    for line in tx_lines:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        from_bank, from_acct = parts[1].strip(), parts[2].strip()
        to_bank, to_acct = parts[3].strip(), parts[4].strip()
        for bank, acct in ((from_bank, from_acct), (to_bank, to_acct)):
            key = make_account_key(bank, acct)
            if key not in seen:
                seen[key] = {
                    "bank": bank,
                    "account": acct,
                    "account_key": key,
                }
    return list(seen.values())


def parse_pattern_file(
    path: str | Path,
    *,
    source_file_label: str | None = None,
) -> tuple[list[IbmPatternInstance], str]:
    """
    Parse Patterns.txt into instances.
    Returns (instances, sha256).
    Raises UnsupportedPatternFormatError if BEGIN/END counts mismatch or structure invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    checksum = file_sha256(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    label = source_file_label or str(path)

    n_begin = sum(
        1 for line in lines if line.strip().upper().startswith("BEGIN LAUNDERING ATTEMPT")
    )
    n_end = sum(
        1 for line in lines if line.strip().upper().startswith("END LAUNDERING ATTEMPT")
    )
    if n_begin == 0:
        raise UnsupportedPatternFormatError(
            f"No BEGIN LAUNDERING ATTEMPT blocks found in {path}"
        )
    if n_begin != n_end:
        raise UnsupportedPatternFormatError(
            f"BEGIN/END mismatch in {path}: begin={n_begin} end={n_end}"
        )

    instances: list[IbmPatternInstance] = []
    i = 0
    record_index = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        begin_m = BEGIN_RE.match(stripped)
        if begin_m:
            raw_type = begin_m.group(1)
            start_line = i + 1  # 1-based
            tx_lines: list[str] = []
            j = i + 1
            end_m = None
            while j < len(lines):
                s = lines[j].strip()
                end_m = END_RE.match(s)
                if end_m:
                    break
                if s.startswith("BEGIN LAUNDERING ATTEMPT"):
                    raise UnsupportedPatternFormatError(
                        f"Nested BEGIN at line {j + 1} before END of block starting {start_line}"
                    )
                if s and not s.startswith("END "):
                    tx_lines.append(s)
                j += 1
            if end_m is None:
                raise UnsupportedPatternFormatError(
                    f"Unclosed BEGIN at line {start_line}"
                )
            end_type = end_m.group(1)
            end_line = j + 1
            canonical = canonicalize_pattern_type(raw_type)
            end_canonical = canonicalize_pattern_type(end_type)
            notes = None
            status = ParseStatus.OK
            if canonical != end_canonical:
                status = ParseStatus.WARN
                notes = f"BEGIN type {raw_type!r} != END type {end_type!r}"

            accounts = _accounts_from_tx_lines(tx_lines)
            if not tx_lines:
                status = ParseStatus.WARN
                notes = (notes + "; " if notes else "") + "empty transaction body"

            inst = IbmPatternInstance(
                instance_id=_stable_instance_id(checksum, start_line, end_line, canonical),
                raw_pattern_name=raw_type,
                pattern_type=canonical,
                source_record_index=record_index,
                parse_status=status,
                source_file=label,
                source_checksum=checksum,
                source_start_line=start_line,
                source_end_line=end_line,
                referenced_accounts=accounts,
                referenced_transactions=None,
                parse_notes=notes,
            )
            inst.validate()
            instances.append(inst)
            record_index += 1
            i = j + 1
            continue

        if END_RE.match(stripped):
            raise UnsupportedPatternFormatError(
                f"Orphan END at line {i + 1} without matching BEGIN"
            )
        # Skip non-block content outside attempts (should be rare)
        i += 1

    if len(instances) != n_begin:
        raise UnsupportedPatternFormatError(
            f"Parsed {len(instances)} instances but counted {n_begin} BEGIN lines"
        )
    return instances, checksum
