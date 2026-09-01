/** Mẫu hình do bộ dò đồ thị tìm được, trình bày dưới dạng TRÌNH TỰ.
 *
 * Tab "Chu trình" trước đây dò chu trình trên vùng đồ thị đang vẽ. Vùng ấy là
 * lân cận một chặng quanh tài khoản có cảnh báo — 48 đỉnh với 47 cạnh, tức một
 * cây — nên về mặt toán học không thể có chu trình. Màn hình vì thế luôn ghi
 * "Chu trình: 0" trong khi cơ sở dữ liệu có 72 chu trình đã dò được.
 *
 * Panel này đọc đúng những mẫu hình ấy. Và nó trình bày theo trình tự thời gian
 * chứ không vẽ thêm một mạng nhện: câu hỏi của chuyên viên là "vòng tiền diễn ra
 * ra sao", mà một danh sách có thứ tự trả lời được, còn đồ thị node-link thì không.
 */

import { AlertTriangle, ArrowDown, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type DetectedPattern } from "../../../api/client";
import { C } from "../../../design/palette";

const PATTERN_LABEL: Record<string, string> = {
  CYCLE: "Chu trình — tiền quay về nơi xuất phát",
  FAN_IN: "Gom vào — nhiều nguồn dồn về một tài khoản",
  FAN_OUT: "Toả ra — một tài khoản chia tiền cho nhiều đích",
};

function money(amount: number | null, currency: string | null): string {
  if (amount === null) return "—";
  return `${amount.toLocaleString("vi-VN", { maximumFractionDigits: 0 })} ${currency ?? ""}`.trim();
}

function gap(hours: number | null): string | null {
  if (hours === null) return null;
  if (hours < 1) return `${Math.round(hours * 60)} phút sau`;
  if (hours < 48) return `${hours.toFixed(1)} giờ sau`;
  return `${(hours / 24).toFixed(1)} ngày sau`;
}

/** Phần trăm tiền giữ lại sau khi đi hết vòng — dấu hiệu đọc được ngay.
 *
 * Chỉ tính cho chu trình: với FAN_IN/FAN_OUT thì chặng đầu và chặng cuối không
 * cùng một dòng tiền nên tỷ lệ này vô nghĩa.
 */
function retained(p: DetectedPattern): string | null {
  if (p.pattern !== "CYCLE" || p.hops.length < 2) return null;
  const first = p.hops[0]?.amount;
  const last = p.hops[p.hops.length - 1]?.amount;
  if (!first || last === null || last === undefined) return null;
  const kept = 1 - last / first;
  if (kept <= 0) return null;
  return `giữ lại ${(kept * 100).toFixed(0)}%`;
}

export function PatternSequencePanel({ accounts }: { accounts: string[] }) {
  const [data, setData] = useState<DetectedPattern[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accounts.length) {
      setData([]);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    // Giới hạn số tài khoản gửi lên: đồ thị có thể vẽ hàng trăm đỉnh, mà chuỗi
    // truy vấn quá dài sẽ bị máy chủ từ chối.
    api
      .graphPatterns(accounts.slice(0, 60), undefined, 25)
      .then((rows) => alive && setData(rows))
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [accounts.join(",")]);

  if (loading && !data) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-2xs text-ink-low">
        <Loader2 size={13} className="animate-spin" /> Đang tra mẫu hình đã dò được…
      </div>
    );
  }
  if (error) {
    return <div className="px-3 py-3 text-2xs text-risk">Không tra được mẫu hình: {error}</div>;
  }
  if (!data?.length) {
    return (
      <div className="px-3 py-3 text-2xs leading-relaxed text-ink-dim">
        Bộ dò đồ thị chưa ghi mẫu hình nào cho các tài khoản đang hiển thị. Thử mở rộng vùng vẽ hoặc chọn một tài khoản
        có cảnh báo từ nhánh đồ thị.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-3 py-2">
      <p className="mb-2 text-3xs text-ink-dim">
        {data.length} mẫu hình do bộ dò đồ thị ghi nhận trên các tài khoản đang hiển thị. Số tiền và thời điểm tra từ sổ
        giao dịch, mỗi chặng kèm mã giao dịch để đối chiếu.
      </p>
      <ol className="flex flex-col gap-2">
        {data.map((p) => {
          const kept = retained(p);
          return (
            <li key={p.evidence_id} className="rounded-control border border-line bg-elev p-2.5">
              <div className="flex flex-wrap items-baseline gap-2">
                <AlertTriangle size={12} style={{ color: C.warn }} className="shrink-0" />
                <span className="text-2xs font-semibold text-ink-hi">
                  {PATTERN_LABEL[p.pattern] ?? p.pattern}
                </span>
                <span className="font-mono text-3xs text-ink-low">
                  {p.hop_count} chặng · {p.accounts.length} tài khoản
                  {p.duration_hours !== null && ` · ${p.duration_hours.toFixed(1)} giờ`}
                </span>
                {kept && (
                  <span className="rounded bg-warn/15 px-1.5 py-0.5 font-mono text-3xs text-warn-soft">{kept}</span>
                )}
              </div>

              <ol className="mt-2 flex flex-col">
                {p.hops.map((h, index) => (
                  <li key={`${h.transaction_id}-${h.seq}`}>
                    {index > 0 && (
                      <div className="flex items-center gap-1.5 py-0.5 pl-1 text-3xs text-ink-dim">
                        <ArrowDown size={10} />
                        {gap(h.gap_hours) ?? "thời điểm không xác định"}
                      </div>
                    )}
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded bg-app px-2 py-1">
                      <span className="font-mono text-3xs text-ink-low">{h.seq}.</span>
                      <span className="tabular font-mono text-3xs text-ink-mid">{h.source}</span>
                      <span className="text-ink-dim">→</span>
                      <span className="tabular font-mono text-3xs text-ink-mid">{h.target}</span>
                      <span className="tabular ml-auto font-mono text-2xs text-ink-hi">
                        {money(h.amount, h.currency)}
                      </span>
                      <span className="w-full font-mono text-3xs text-ink-dim">
                        {h.occurred_at ? new Date(h.occurred_at).toLocaleString("vi-VN") : "—"} · giao dịch{" "}
                        {h.transaction_id}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
