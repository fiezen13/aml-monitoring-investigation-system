import { useMemo, useState } from "react";

import type { FcTxRow } from "../../../api/client";
import { usd } from "../../../api/fcFormat";
import { Empty, Skeleton } from "../../../components/fc/primitives";

type SortKey = "occurred_at" | "amount";

interface Props {
  rows: FcTxRow[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  /** Tiêu đề phạm vi, ví dụ "PT-Gate → Tài khoản gom 1". */
  scopeLabel: string;
  /** Tổng theo từng loại tiền, lấy từ metric của cạnh. */
  amountsByCurrency: Record<string, number>;
  selectedId: number | null;
  onPick: (row: FcTxRow) => void;
  onPage: (page: number) => void;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Bảng giao dịch của quan hệ đang chọn.
 *
 * Đây là thứ mà màn hình cũ không có: tab "Giao dịch" trước đây liệt kê *quan
 * hệ* chứ không phải giao dịch, nên analyst không có đường nào đi từ một cạnh
 * xuống tới các lần chuyển khoản làm nên cạnh đó.
 *
 * Sắp xếp làm ở phía client vì mỗi lần chỉ có một trang trong tay; phân trang
 * thì gọi lại API. Trộn hai cơ chế sẽ cho ra thứ tự sai khi sang trang, nên cột
 * sắp xếp cố ý chỉ đổi thứ tự *trong trang đang xem* và nói rõ điều đó.
 */
export function TransactionTable({
  rows,
  total,
  page,
  pageSize,
  loading,
  error,
  scopeLabel,
  amountsByCurrency,
  selectedId,
  onPick,
  onPage,
}: Props) {
  const [sort, setSort] = useState<SortKey>("occurred_at");
  const [desc, setDesc] = useState(true);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const va = sort === "amount" ? a.amount : new Date(a.occurred_at).getTime();
      const vb = sort === "amount" ? b.amount : new Date(b.occurred_at).getTime();
      return desc ? vb - va : va - vb;
    });
    return copy;
  }, [rows, sort, desc]);

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const currencies = Object.entries(amountsByCurrency);

  const header = (key: SortKey, label: string) => (
    <button
      type="button"
      onClick={() => {
        if (sort === key) setDesc((d) => !d);
        else {
          setSort(key);
          setDesc(true);
        }
      }}
      className="inline-flex items-center gap-1 text-3xs font-medium uppercase tracking-[0.08em] text-ink-dim transition-colors hover:text-ink-soft"
    >
      {label}
      {sort === key && <span aria-hidden>{desc ? "↓" : "↑"}</span>}
    </button>
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line-faint px-3 py-2">
        <span className="text-2xs font-semibold text-ink-hi">{scopeLabel}</span>
        <span className="tabular font-mono text-2xs text-ink-soft">{total} giao dịch</span>
        {currencies.map(([ccy, amount]) => (
          <span key={ccy} className="tabular font-mono text-2xs text-ink-soft">
            {ccy === "USD" ? usd(amount) : `${amount.toLocaleString("vi-VN")} ${ccy}`}
          </span>
        ))}
      </div>

      {loading && <Skeleton rows={5} />}

      {!loading && error && (
        <p className="px-3 py-4 text-2xs leading-relaxed text-risk-soft">{error}</p>
      )}

      {/* §41: không có giao dịch thì nói thẳng, không dựng ra một dòng nào. */}
      {!loading && !error && !rows.length && (
        <Empty
          text="Không có bằng chứng giao dịch"
          hint="Quan hệ này không có chuyển khoản ngân hàng nào đứng sau — quan hệ sở hữu, thiết bị dùng chung và chuyển trên chuỗi đều như vậy."
        />
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <table className="w-full text-2xs">
            <thead className="sticky top-0 bg-side">
              <tr className="border-b border-line text-left">
                <th className="px-3 py-1.5">{header("occurred_at", "Thời điểm")}</th>
                <th className="px-3 py-1.5 text-3xs font-medium uppercase tracking-[0.08em] text-ink-dim">Mã</th>
                <th className="px-3 py-1.5 text-3xs font-medium uppercase tracking-[0.08em] text-ink-dim">Từ</th>
                <th className="px-3 py-1.5 text-3xs font-medium uppercase tracking-[0.08em] text-ink-dim">Đến</th>
                <th className="px-3 py-1.5 text-right">{header("amount", "Số tiền")}</th>
                <th className="px-3 py-1.5 text-3xs font-medium uppercase tracking-[0.08em] text-ink-dim">Kênh</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => onPick(r)}
                  className={`cursor-pointer border-b border-line-faint transition-colors ${
                    selectedId === r.id ? "bg-primary-soft" : "hover:bg-elev"
                  }`}
                >
                  <td className="tabular px-3 py-1.5 font-mono text-ink-soft">{fmtTime(r.occurred_at)}</td>
                  <td className="tabular px-3 py-1.5 font-mono text-info-soft">TX-{r.id}</td>
                  <td className="tabular truncate-1 px-3 py-1.5 font-mono text-ink-low">{r.from_account}</td>
                  <td className="tabular truncate-1 px-3 py-1.5 font-mono text-ink-low">{r.to_account}</td>
                  <td className="tabular px-3 py-1.5 text-right font-mono text-ink-hi">
                    {r.currency === "USD" ? usd(r.amount) : `${r.amount.toLocaleString("vi-VN")} ${r.currency}`}
                  </td>
                  <td className="px-3 py-1.5 text-ink-soft">{r.channel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex flex-none items-center justify-between border-t border-line-faint px-3 py-1.5 text-2xs text-ink-low">
          <span className="tabular font-mono">
            Trang {page}/{pages}
          </span>
          <span className="flex gap-1.5">
            <button type="button" className="fc-btn py-0.5" disabled={page <= 1} onClick={() => onPage(page - 1)}>
              ‹ Trước
            </button>
            <button type="button" className="fc-btn py-0.5" disabled={page >= pages} onClick={() => onPage(page + 1)}>
              Sau ›
            </button>
          </span>
        </div>
      )}
    </div>
  );
}
