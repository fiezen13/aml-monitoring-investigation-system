-- ---------------------------------------------------------------------
-- 010 — Địa lý ngân hàng cho World Monitor
--
-- Bộ IBM AML chỉ mang mã ngân hàng và số tài khoản, không có quốc gia. Nhưng
-- file `*_accounts.csv` đi kèm có cột `Bank Name`, và phần lớn tên đã chứa sẵn
-- quốc gia (`China Bank #2820`). Hai bảng dưới đây biến thứ đó thành dữ liệu
-- truy vấn được, và ghi rõ phần nào là đọc ra được, phần nào là gán.
--
-- Không có khoá ngoại từ `account` sang `bank`: dữ liệu mẫu (seed_data.py) sinh
-- mã ngân hàng ở một không gian khác với bộ IBM, nên ràng buộc cứng sẽ chặn
-- việc nạp dữ liệu mẫu. Quan hệ là LEFT JOIN, tài khoản chưa biết ngân hàng thì
-- không có quốc gia — và bản đồ phải nói ra điều đó thay vì đoán.
-- ---------------------------------------------------------------------

CREATE TABLE bank (
    -- Mã ngân hàng như trong `*_Trans.csv`, cũng là `account.bank_code`.
    -- KHÔNG phải cột `Bank ID` của `*_accounts.csv` — hai không gian ID khác
    -- nhau, nối nhầm sẽ ra rỗng mà không báo lỗi. Khoá nối đúng giữa hai file
    -- là số tài khoản.
    bank_code      TEXT        PRIMARY KEY,
    bank_name      TEXT        NOT NULL,
    country_code   CHAR(2),
    -- parsed   — quốc gia đọc thẳng từ tên ngân hàng, không suy diễn.
    -- assigned — tên ngân hàng hư cấu, quốc gia do dự án gán để bản đồ dùng được.
    -- unknown  — chưa xác định; country_code phải NULL.
    country_source TEXT        NOT NULL CHECK (country_source IN ('parsed', 'assigned', 'unknown')),
    -- Nhà cung cấp dịch vụ tài sản mã hoá. Trong bộ LI-Small, tài khoản thuộc
    -- `Crytpo Bank` có 99,95% giao dịch bằng Bitcoin và chiếm 90,8% toàn bộ
    -- Bitcoin của bộ dữ liệu — đây là hành vi đo được, không phải suy đoán từ tên.
    is_vasp        BOOLEAN     NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bank_unknown_has_no_country CHECK (
        (country_source = 'unknown') = (country_code IS NULL)
    )
);

CREATE INDEX bank_country_idx ON bank (country_code);

COMMENT ON TABLE bank IS
    'Chiều ngân hàng suy ra từ *_accounts.csv. Dữ liệu tổng hợp, ngân hàng không có thật.';
COMMENT ON COLUMN bank.country_source IS
    'Nguồn của country_code. `assigned` là lựa chọn trình bày của dự án, không phải dữ kiện — '
    'giữ cột này để khi thay bằng dữ liệu thật, không ai kế thừa quốc gia gán mà không biết.';

-- ---------------------------------------------------------------------
-- Toạ độ quốc gia cho bản đồ.
--
-- Tách khỏi `fc.hub`: bảng đó thuộc lớp mô phỏng Financial City, có phiên bản
-- theo thời gian và mức rủi ro pháp vực. `/world` đã cố tình tách chế độ
-- operational khỏi simulation, trộn hai nguồn vào một bảng sẽ xoá ranh giới đó.
--
-- Cố ý KHÔNG có cột `jurisdiction_risk`. Gán quốc gia là mô tả dữ liệu; gán mức
-- rủi ro pháp vực là phán đoán chính sách và theo `fc.hub` thì nhãn ấy phải có
-- thời điểm hiệu lực. Nếu sau này cần, thêm bằng một migration riêng có ngày.
-- ---------------------------------------------------------------------

CREATE TABLE country_geo (
    country_code CHAR(2)       PRIMARY KEY,
    name         TEXT          NOT NULL,
    lat          NUMERIC(6, 3) NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon          NUMERIC(7, 3) NOT NULL CHECK (lon BETWEEN -180 AND 180)
);

COMMENT ON TABLE country_geo IS
    'Toạ độ đại diện của quốc gia để vẽ bản đồ World Monitor. Không mang ý nghĩa nghiệp vụ.';
