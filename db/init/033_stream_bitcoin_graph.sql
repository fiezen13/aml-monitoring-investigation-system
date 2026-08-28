-- 033 · Đồ thị Bitcoin TĂNG DẦN cho streaming (Pha 1 — nhánh Bitcoin).
--
-- Khác nhánh ngân hàng: đồ thị Bitcoin là GIAO DỊCH → GIAO DỊCH (không phải
-- account → account). Node = một giao dịch on-chain; cạnh = dòng tiền giữa hai
-- giao dịch (từ edgelist Elliptic — trong Bitcoin thật là input/output).
--
-- "Tăng dần": mỗi giao dịch stream tới → thêm node; cạnh tới láng giềng chỉ được
-- vật chất hoá KHI cả hai đầu đã tới (back-fill khi đầu kia tới sau) — đúng thực
-- tế "dựng từng cạnh một".

CREATE TABLE IF NOT EXISTS stream_bitcoin_tx (
    tx_id        TEXT PRIMARY KEY,
    timestep     INTEGER,
    arrived_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stream_bitcoin_edge (
    src_tx     TEXT NOT NULL,
    dst_tx     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (src_tx, dst_tx)
);
CREATE INDEX IF NOT EXISTS stream_btc_edge_dst_idx ON stream_bitcoin_edge (dst_tx);
