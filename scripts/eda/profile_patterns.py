"""EDA file pattern của bộ IBM AML.

File `*_Patterns.txt` liệt kê các kịch bản rửa tiền đã được tiêm vào dữ liệu,
mỗi kịch bản là một khối:

    BEGIN LAUNDERING ATTEMPT - <TÊN TYPOLOGY>: <mô tả>
    <các dòng giao dịch, cùng định dạng 11 cột như file Trans>
    END LAUNDERING ATTEMPT - <TÊN TYPOLOGY>

Script này trả lời bốn câu hỏi quyết định phạm vi đánh giá của dự án:

1. IBM cung cấp những typology nào, mỗi loại bao nhiêu instance?
   → Quyết định typology nào trong danh mục T01-T10 có ground truth thật,
     typology nào phải tự sinh hoặc phải rút khỏi cam kết (BUS-001 §7).

2. Một instance lớn cỡ nào và trải qua bao nhiêu ngày?
   → Quyết định bán kính subgraph cần dựng, và cho biết instance có bị
     vắt qua mốc cắt khi chia tập hay không.

3. Bao nhiêu tài khoản thuộc nhiều instance?
   → Nếu > 0 thì việc gom instance BẮT BUỘC phải là một lượt duyệt thành
     phần liên thông, không phải vòng lặp theo từng network. Bỏ qua điều
     này thì hai instance dính nhau bị tách về hai tập và model học thuộc
     mạng lưới.

4. Kênh thanh toán và tiền tệ bên trong pattern lệch thế nào?
   → Nếu gần như toàn bộ pattern dùng một kênh thì kênh đó là chữ ký của
     bộ sinh dữ liệu, không phải đặc điểm của rửa tiền, và phải bị loại
     khỏi đặc trưng model.

Chạy:
    python scripts/eda/profile_patterns.py \
        --input data/raw/ibm-aml/LI-Small-Patterns.txt \
        --output artifacts/eda/li_small_patterns.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Vị trí cột trong dòng giao dịch. Giống hệt file Trans, xem profile_transactions.py.
C_TS, C_FROM_BANK, C_FROM_ACCT, C_TO_BANK, C_TO_ACCT = 0, 1, 2, 3, 4
C_CURRENCY_RECEIVED, C_FORMAT = 6, 9

BEGIN = "BEGIN LAUNDERING ATTEMPT"
END = "END LAUNDERING ATTEMPT"


def normalize_bank(bank: str) -> str:
    """Bỏ số 0 đứng đầu.

    Cùng một ngân hàng xuất hiện dưới cả `020` lẫn `0020`. Không chuẩn hoá
    thì hai tài khoản của cùng một ngân hàng bị coi là của hai ngân hàng
    khác nhau, và khoá tài khoản ghép ra sai — lỗi im lặng, không có thông
    báo nào, chỉ có cạnh giả trong đồ thị.
    """
    return bank.lstrip("0") or "0"


def account_key(bank: str, account: str) -> str:
    """Khoá tài khoản là `bank:account`, không phải chỉ `account`.

    Số tài khoản chỉ duy nhất trong phạm vi một ngân hàng.
    """
    return f"{normalize_bank(bank)}:{account}"


def quantiles(values: list[int]) -> dict[str, Any]:
    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    return {
        "min": ordered[0],
        "p50": ordered[n // 2],
        "max": ordered[-1],
        "tong": sum(ordered),
    }


def profile(path: Path) -> dict[str, Any]:
    typology_counts: Counter[str] = Counter()
    txns_per_instance: defaultdict[str, list[int]] = defaultdict(list)
    accounts_per_instance: defaultdict[str, list[int]] = defaultdict(list)
    days_per_instance: defaultdict[str, list[int]] = defaultdict(list)
    formats: Counter[str] = Counter()
    currencies: Counter[str] = Counter()
    membership: Counter[str] = Counter()
    all_pattern_accounts: set[str] = set()

    instances = 0
    unterminated = 0
    total_pattern_txns = 0

    current_typology: str | None = None
    current_rows: list[str] = []

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")

            if line.startswith(BEGIN):
                if current_typology is not None:
                    # Khối trước chưa có dòng END — file thật có trường hợp này.
                    unterminated += 1
                match = re.search(r"-\s*([A-Z\-]+)", line[len(BEGIN) :])
                current_typology = match.group(1).strip() if match else "UNKNOWN"
                current_rows = []
                continue

            if line.startswith(END):
                if current_typology and current_rows:
                    instances += 1
                    typology_counts[current_typology] += 1
                    accounts: set[str] = set()
                    dates: set[str] = set()
                    for row in current_rows:
                        parts = row.split(",")
                        if len(parts) < 11:
                            continue
                        accounts.add(account_key(parts[C_FROM_BANK], parts[C_FROM_ACCT]))
                        accounts.add(account_key(parts[C_TO_BANK], parts[C_TO_ACCT]))
                        dates.add(parts[C_TS][:10])
                        formats[parts[C_FORMAT]] += 1
                        currencies[parts[C_CURRENCY_RECEIVED]] += 1
                    total_pattern_txns += len(current_rows)
                    txns_per_instance[current_typology].append(len(current_rows))
                    accounts_per_instance[current_typology].append(len(accounts))
                    days_per_instance[current_typology].append(len(dates))
                    for account in accounts:
                        membership[account] += 1
                    all_pattern_accounts |= accounts
                current_typology = None
                current_rows = []
                continue

            if line.strip() and current_typology is not None:
                current_rows.append(line)

    shared = sum(1 for count in membership.values() if count > 1)
    total_format_rows = sum(formats.values()) or 1

    return {
        "nguon": {
            "file": path.name,
            "kich_thuoc_byte": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "tong_quan": {
            "so_instance_hoan_chinh": instances,
            "so_khoi_thieu_dong_END": unterminated,
            "so_giao_dich_trong_pattern": total_pattern_txns,
            "so_tai_khoan_trong_pattern": len(all_pattern_accounts),
            "so_tai_khoan_thuoc_nhieu_instance": shared,
        },
        "typology": {
            name: {
                "so_instance": count,
                "giao_dich_moi_instance": quantiles(txns_per_instance[name]),
                "tai_khoan_moi_instance": quantiles(accounts_per_instance[name]),
                "so_ngay_trai_qua": quantiles(days_per_instance[name]),
            }
            for name, count in typology_counts.most_common()
        },
        "kenh_thanh_toan_trong_pattern": [
            {"kenh": k, "so_dong": v, "ti_le_pct": round(100 * v / total_format_rows, 2)}
            for k, v in formats.most_common()
        ],
        "tien_te_trong_pattern": formats and [{"tien_te": k, "so_dong": v} for k, v in currencies.most_common(10)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = profile(args.input)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Đã ghi {args.output}")
    print(text)


if __name__ == "__main__":
    main()
