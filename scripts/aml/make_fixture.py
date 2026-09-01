"""Sinh file CSV mẫu dùng cho kiểm thử luồng nạp AML.

Bộ dữ liệu thật của IBM nặng hàng trăm megabyte tới hàng chục gigabyte và
**không** được commit vào Git. Kiểm thử vẫn cần một file có đúng lược đồ đó,
nên file này sinh ra một bản nhỏ, tất định, và cố ý chứa những trường hợp
biên mà luồng nạp phải xử lý đúng:

* nhãn `Is Laundering` cả 0 lẫn 1 — mang theo nguyên trạng, không dùng để lọc;
* giao dịch cùng tài khoản gửi và nhận (tái đầu tư) — không được loại;
* giao dịch cùng ngân hàng gửi và nhận — không được loại;
* giao dịch khác đơn vị tiền giữa bên trả và bên nhận;
* số tiền rất nhỏ và rất lớn — không được loại;
* mã ngân hàng có số 0 ở đầu, số tài khoản dạng hexadecimal;
* thời gian không sắp xếp tăng dần hoàn toàn;
* các dòng hỏng: thiếu trường, thời gian sai, số tiền âm, nhãn sai.

    python scripts/aml/make_fixture.py --rows 200 --out tests/fixtures/aml/HI-Sample_Trans.csv
"""

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

HEADER = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,"
    "Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering"
)

BANKS = ["010", "015768", "0", "001234", "070", "08812"]
CURRENCIES = ["US Dollar", "Euro", "Yuan", "Bitcoin", "Vietnamese Dong"]
FORMATS = ["Reinvestment", "Cheque", "Credit Card", "ACH", "Wire", "Cash"]

# Bốn dòng hỏng, mỗi dòng một loại lỗi khác nhau. Chèn vào giữa file để
# chứng minh một dòng hỏng không làm dừng cả lượt nạp.
MALFORMED_ROWS = [
    # thiếu trường
    "2022/09/01 00:15,010,80A1B2C30,015768,8149656B0,110.00,US Dollar,110.00,US Dollar",
    # thời gian không đọc được
    "hôm qua,010,80A1B2C30,015768,8149656B0,110.00,US Dollar,110.00,US Dollar,Cheque,0",
    # số tiền âm
    "2022/09/01 00:16,010,80A1B2C30,015768,8149656B0,-5.00,US Dollar,-5.00,US Dollar,Cheque,0",
    # nhãn không phải 0 hoặc 1
    "2022/09/01 00:17,010,80A1B2C30,015768,8149656B0,5.00,US Dollar,5.00,US Dollar,Cheque,yes",
]


def account_id(rng: random.Random) -> str:
    """Số tài khoản kiểu bộ IBM: 8 chữ số hex viết hoa rồi một chữ số."""
    return f"{rng.randrange(16**8):08X}{rng.randrange(10)}"


def build_rows(rows: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    accounts = [account_id(rng) for _ in range(max(rows // 4, 8))]
    start = datetime(2022, 9, 1, 0, 0)
    out: list[str] = []

    for index in range(rows):
        # Thời gian nhích dần nhưng thỉnh thoảng lùi lại, giống dữ liệu thật
        # và đủ để chứng minh chế độ event-time không bao giờ ngủ âm.
        moment = start + timedelta(minutes=index) - timedelta(minutes=rng.choice([0, 0, 0, 3]))
        from_bank = rng.choice(BANKS)
        to_bank = from_bank if index % 11 == 0 else rng.choice(BANKS)
        from_account = rng.choice(accounts)
        to_account = from_account if index % 13 == 0 else rng.choice(accounts)

        if index % 17 == 0:
            amount_paid, paid_ccy = "0.00000340", "Bitcoin"
            amount_received, received_ccy = "142.55", "US Dollar"
        elif index % 23 == 0:
            amount_paid = amount_received = f"{rng.randrange(50_000_000, 90_000_000)}.99"
            paid_ccy = received_ccy = "Vietnamese Dong"
        else:
            amount = f"{rng.randrange(1, 5_000_000) / 100:.2f}"
            amount_paid = amount_received = amount
            paid_ccy = received_ccy = rng.choice(CURRENCIES[:3])

        is_laundering = 1 if index % 19 == 0 else 0
        out.append(
            ",".join(
                [
                    moment.strftime("%Y/%m/%d %H:%M"),
                    from_bank,
                    from_account,
                    to_bank,
                    to_account,
                    amount_received,
                    received_ccy,
                    amount_paid,
                    paid_ccy,
                    rng.choice(FORMATS),
                    str(is_laundering),
                ]
            )
        )

    for offset, bad in enumerate(MALFORMED_ROWS):
        out.insert(min(len(out), 20 + offset * 25), bad)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=200, help="Số dòng hợp lệ")
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/aml/HI-Sample_Trans.csv"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER, *build_rows(args.rows, args.seed)]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(lines)} dòng ({args.rows} hợp lệ, {len(MALFORMED_ROWS)} hỏng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
