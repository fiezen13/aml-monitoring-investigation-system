import { useEffect, useState } from "react";

import { api } from "../api/client";
import { int } from "../api/fcFormat";
import { datasetLabel, formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { useConsole } from "../context/ConsoleContext";
import { PageShell } from "../components/ui";
import { Empty, Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";

/**
 * Transaction Explorer — duyệt giao dịch thô có phân trang.
 *
 * Phân trang ở phía máy chủ chứ không tải hết rồi lọc trong trình duyệt: bảng
 * giao dịch là bảng lớn nhất của hệ thống và sẽ còn lớn nữa.
 */

const COLS = "190px 145px 150px 150px 160px 160px 90px 96px";
const CHANNELS = ["all", "CHEQUE", "CREDIT_CARD", "ACH", "CASH", "WIRE", "BITCOIN"];
const PAGE_SIZE = 50;

export function TransactionsPage() {
  const { dataset } = useConsole();
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("all");
  const [minAmount, setMinAmount] = useState("");
  const [minScore, setMinScore] = useState("");
  const [decision, setDecision] = useState("all");
  const [page, setPage] = useState(1);

  // Đổi bộ dữ liệu ở header thì về trang 1: số trang của bộ cũ không có nghĩa
  // với bộ mới (SAML-D ít dòng hơn IBM nhiều lần).
  useEffect(() => setPage(1), [dataset]);

  // `q` và `minAmount` đi thẳng vào deps: mỗi ký tự là một lượt gọi. Với bảng
  // này thì chấp nhận được vì truy vấn có chỉ mục và giới hạn 50 dòng; nếu sau
  // này chậm thì thêm debounce ở đây chứ không đổi hợp đồng API.
  const data = useApi(
    () =>
      api.transactions({
        q: q.trim() || undefined,
        channel: channel === "all" ? undefined : channel,
        min_amount: minAmount ? Number(minAmount) : undefined,
        min_score: minScore ? Number(minScore) / 100 : undefined,
        triggered: decision === "all" ? undefined : decision === "alert",
        dataset,
        page,
        page_size: PAGE_SIZE,
      }),
    [q, channel, minAmount, minScore, decision, dataset, page],
  );

  const total = data.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Tra cứu giao dịch"
        meta={`Bộ dữ liệu ${datasetLabel(dataset)} · ${int(total)} giao dịch khớp bộ lọc · trang ${page}/${pageCount}`}
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
            setMinAmount(e.target.value.replace(/[^\d.]/g, ""));
            setPage(1);
          }}
          placeholder="Số tiền tối thiểu"
          inputMode="decimal"
          aria-label="Số tiền tối thiểu"
          className="fc-input w-[150px]"
        />
        <input
          value={minScore}
          onChange={(e) => {
            setMinScore(e.target.value.replace(/[^\d.]/g, ""));
            setPage(1);
          }}
          placeholder="Điểm tối thiểu (%)"
          inputMode="decimal"
          aria-label="Điểm mô hình tối thiểu"
          className="fc-input w-[160px]"
        />
        <select
          value={decision}
          onChange={(e) => {
            setDecision(e.target.value);
            setPage(1);
          }}
          aria-label="Kết quả mô hình"
          className="fc-input"
        >
          <option value="all">Kết quả: tất cả</option>
          <option value="alert">Vượt ngưỡng</option>
          <option value="below">Dưới ngưỡng</option>
        </select>
        {(q || channel !== "all" || minAmount || minScore || decision !== "all") && (
          <button
            type="button"
            onClick={() => {
              setQ("");
              setChannel("all");
              setMinAmount("");
              setMinScore("");
              setDecision("all");
              setPage(1);
            }}
            className="fc-btn"
          >
            Bỏ lọc
          </button>
        )}
      </div>

      {/* Reinvestment (tái đầu tư) trong bộ IBM đều là chuyển khoản tự-thân
          (from = to). Đường ống ingestion cố ý loại mọi self-loop nên loại này
          không xuất hiện — nói rõ để chuyên viên khỏi tưởng thiếu dữ liệu. */}
      {dataset === "ibm_hi_medium" && (
        <p className="-mt-0.5 text-2xs leading-relaxed text-ink-low">
          Không thấy giao dịch <span className="font-medium text-ink-soft">Reinvestment</span> (tái đầu tư)? Trong bộ
          IBM, đây là chuyển khoản tự-thân — tài khoản chuyển cho chính nó — nên đường ống cố ý loại khỏi bảng: self-loop
          không phải dòng tiền giữa hai bên và không có tín hiệu cho phân tích mạng lưới.
        </p>
      )}

      <Panel bodyClassName="overflow-x-auto px-0">
        <div className="min-w-[1240px]">
          <div
            className="sticky top-0 grid gap-2 border-b border-line bg-panel px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
            style={{ gridTemplateColumns: COLS }}
          >
            <span>Mã nguồn</span>
            <span>Thời điểm</span>
            <span>Từ tài khoản</span>
            <span>Đến tài khoản</span>
            <span className="text-right">Amount Paid</span>
            <span className="text-right">Amount Received</span>
            <span>Kênh</span>
            <span className="text-right">Điểm model</span>
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
              <span className="truncate-1 font-mono text-2xs text-ink-low" title={r.source_id ?? String(r.id)}>
                {r.source_id ?? r.id}
              </span>
              <span className="text-xs text-ink-soft">{formatDateTime(r.occurred_at)}</span>
              <span className="truncate-1 font-mono text-xs">{r.from_account}</span>
              <span className="truncate-1 font-mono text-xs">{r.to_account}</span>
              <span className="tabular text-right font-mono text-xs" title="Giá trị gốc; không quy đổi USD">
                {r.amount.toLocaleString("vi-VN", { maximumFractionDigits: 8 })} {r.currency}
              </span>
              <span className="tabular text-right font-mono text-xs" title="Giá trị nhận gốc; không quy đổi USD">
                {r.amount_received?.toLocaleString("vi-VN", { maximumFractionDigits: 8 }) ?? "—"}{" "}
                {r.receiving_currency ?? ""}
              </span>
              <span className="text-xs text-ink-soft">{r.channel}</span>
              <span
                className={`tabular text-right font-mono text-xs ${r.triggered ? "text-risk-soft" : "text-ink-soft"}`}
                title={r.threshold == null ? undefined : `Ngưỡng ${(r.threshold * 100).toFixed(4)}%`}
              >
                {r.model_score == null ? "—" : `${(r.model_score * 100).toFixed(4)}%`}
                {r.triggered ? " · ALERT" : ""}
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
    </PageShell>
  );
}
