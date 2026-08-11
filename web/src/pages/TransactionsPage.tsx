import { useState } from "react";

import { api } from "../api/client";
import { int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { Empty, Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";

/**
 * Transaction Explorer — duyệt giao dịch thô có phân trang.
 *
 * Phân trang ở phía máy chủ chứ không tải hết rồi lọc trong trình duyệt: bảng
 * giao dịch là bảng lớn nhất của hệ thống và sẽ còn lớn nữa.
 */

const COLS = "72px 150px 150px 150px 110px 70px 100px 1fr";
const CHANNELS = ["all", "transfer", "cash", "card", "wire"];
const PAGE_SIZE = 50;

export function TransactionsPage() {
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("all");
  const [minAmount, setMinAmount] = useState("");
  const [page, setPage] = useState(1);

  // `q` và `minAmount` đi thẳng vào deps: mỗi ký tự là một lượt gọi. Với bảng
  // này thì chấp nhận được vì truy vấn có chỉ mục và giới hạn 50 dòng; nếu sau
  // này chậm thì thêm debounce ở đây chứ không đổi hợp đồng API.
  const data = useApi(
    () =>
      api.transactions({
        q: q.trim() || undefined,
        channel: channel === "all" ? undefined : channel,
        min_amount: minAmount ? Number(minAmount) : undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [q, channel, minAmount, page],
  );

  const total = data.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex animate-up flex-col gap-3 p-4">
      <ScreenTitle
        title="Transaction Explorer"
        meta={`${int(total)} giao dịch khớp bộ lọc · trang ${page}/${pageCount}`}
      />

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder="Lọc theo tài khoản hoặc nội dung…"
          aria-label="Lọc giao dịch"
          className="fc-input w-[280px]"
        />
        <select
          value={channel}
          onChange={(e) => {
            setChannel(e.target.value);
            setPage(1);
          }}
          aria-label="Kênh"
          className="fc-input"
        >
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {c === "all" ? "Kênh: tất cả" : c}
            </option>
          ))}
        </select>
        <input
          value={minAmount}
          onChange={(e) => {
            setMinAmount(e.target.value.replace(/\D/g, ""));
            setPage(1);
          }}
          placeholder="Số tiền tối thiểu"
          inputMode="numeric"
          aria-label="Số tiền tối thiểu"
          className="fc-input w-[150px]"
        />
        {(q || channel !== "all" || minAmount) && (
          <button
            type="button"
            onClick={() => {
              setQ("");
              setChannel("all");
              setMinAmount("");
              setPage(1);
            }}
            className="fc-btn"
          >
            Bỏ lọc
          </button>
        )}
      </div>

      <Panel bodyClassName="overflow-x-auto px-0">
        <div className="min-w-[900px]">
          <div
            className="sticky top-0 grid gap-2 border-b border-line bg-panel px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
            style={{ gridTemplateColumns: COLS }}
          >
            <span>ID</span>
            <span>Thời điểm</span>
            <span>Từ tài khoản</span>
            <span>Đến tài khoản</span>
            <span className="text-right">Số tiền</span>
            <span>Tiền tệ</span>
            <span>Kênh</span>
            <span>Nội dung</span>
          </div>

          {data.loading && <Skeleton rows={8} />}
          {data.error && <div className="px-3 py-6 text-sm text-risk-soft">{data.error}</div>}
          {!data.loading && !data.error && !data.data?.rows.length && (
            <Empty text="Không có giao dịch nào khớp bộ lọc" hint="Thử bỏ bớt điều kiện lọc" />
          )}

          {data.data?.rows.map((r) => (
            <div
              key={r.id}
              className="grid items-center gap-2 border-b border-line-faint px-3 py-[7px] text-base transition-colors hover:bg-elev"
              style={{ gridTemplateColumns: COLS }}
            >
              <span className="font-mono text-2xs text-ink-low">{r.id}</span>
              <span className="text-xs text-ink-soft">{formatDateTime(r.occurred_at)}</span>
              <span className="truncate-1 font-mono text-xs">{r.from_account}</span>
              <span className="truncate-1 font-mono text-xs">{r.to_account}</span>
              <span className="tabular text-right font-mono text-xs">
                {r.amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}
              </span>
              <span className="text-xs text-ink-soft">{r.currency}</span>
              <span className="text-xs text-ink-soft">{r.channel}</span>
              {/* Nội dung do người dùng cuối nhập — hiển thị như dữ liệu thuần,
                  không bao giờ diễn giải như chỉ dẫn (ARC-001 mục 5.2). */}
              <span className="truncate-1 text-xs text-ink-low" title={r.remarks}>
                {r.remarks || "—"}
              </span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="flex items-center justify-between text-sm text-ink-soft">
        <span>
          Hiển thị {data.data?.rows.length ?? 0} trong {int(total)} giao dịch
        </span>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="fc-btn disabled:opacity-40">
            ← Trước
          </button>
          <span className="tabular font-mono text-xs">
            {page} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            disabled={page >= pageCount}
            className="fc-btn disabled:opacity-40"
          >
            Sau →
          </button>
        </div>
      </div>
    </div>
  );
}
