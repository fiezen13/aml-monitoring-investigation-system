import { Crosshair } from "lucide-react";

import type { FcTxRow } from "../../../api/client";
import { usd } from "../../../api/fcFormat";
import { Chip } from "../../../components/fc/primitives";
import { C } from "../../../design/palette";

interface Props {
  tx: FcTxRow;
  /** Nhãn hai đầu quan hệ, để analyst không phải tự dịch account_key sang tên. */
  fromLabel: string;
  toLabel: string;
  onHighlight: () => void;
  onClose: () => void;
}

/**
 * Chi tiết một giao dịch.
 *
 * Nút "Soi trên đồ thị" là thứ đóng vòng: từ đồ thị xuống danh sách giao dịch,
 * rồi từ một giao dịch quay ngược lên đúng quan hệ sinh ra nó. Thiếu chiều
 * ngược đó thì bảng giao dịch chỉ là một cái bảng nữa nằm cạnh đồ thị.
 */
export function TransactionDetail({ tx, fromLabel, toLabel, onHighlight, onClose }: Props) {
  const rows: [string, string][] = [
    ["Thời điểm", new Date(tx.occurred_at).toLocaleString("vi-VN")],
    ["Mã giao dịch", `TX-${tx.id}`],
    ["Tài khoản gửi", tx.from_account],
    ["Tài khoản nhận", tx.to_account],
    ["Số tiền", tx.currency === "USD" ? usd(tx.amount) : `${tx.amount.toLocaleString("vi-VN")} ${tx.currency}`],
    ["Loại tiền", tx.currency],
    ["Kênh", tx.channel],
  ];

  return (
    <div className="animate-up">
      <div className="flex items-center gap-2">
        <Chip color={C.info}>GIAO DỊCH</Chip>
        <div className="tabular flex-1 font-mono text-base font-semibold text-ink-hi">TX-{tx.id}</div>
        <button type="button" onClick={onClose} aria-label="Đóng chi tiết giao dịch" className="text-ink-low hover:text-ink-hi">
          ✕
        </button>
      </div>

      <div className="mt-2 text-xs text-ink-mid">
        <span className="text-ink-soft">{fromLabel}</span>
        <span className="mx-1.5 text-ink-low">→</span>
        <span className="text-ink-soft">{toLabel}</span>
      </div>

      <dl className="mt-3 divide-y divide-line-faint">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 py-1.5">
            <dt className="text-2xs text-ink-low">{k}</dt>
            <dd className="tabular truncate-1 text-right font-mono text-2xs text-ink-hi">{v}</dd>
          </div>
        ))}
      </dl>

      {/* `remarks` là nội dung do người dùng cuối nhập. Là DỮ LIỆU, không phải
          chỉ dẫn — hiển thị nguyên văn, không diễn giải, không thực thi. */}
      {tx.remarks && (
        <div className="mt-3 rounded-control bg-sunken px-2.5 py-2">
          <div className="fc-eyebrow mb-1">Nội dung chuyển khoản</div>
          <p className="whitespace-pre-wrap break-words text-2xs leading-relaxed text-ink-mid">{tx.remarks}</p>
        </div>
      )}

      <button type="button" onClick={onHighlight} className="fc-btn mt-3 flex w-full items-center justify-center gap-1.5">
        <Crosshair size={13} strokeWidth={1.7} aria-hidden />
        Soi trên đồ thị
      </button>
    </div>
  );
}
