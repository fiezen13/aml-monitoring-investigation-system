import { api } from "../api/client";
import { shortAddr, usd } from "../api/fcFormat";
import { formatDate } from "../api/format";
import { useApi } from "../api/useApi";
import { ErrorState, PageShell } from "../components/ui";
import { Chip, Empty, Panel, ProgressBar, RiskScore, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * Project Risk — dự án tài sản mã hoá (kịch bản VN-CA-01).
 *
 * Mỗi đặc trưng hiển thị ở đây đều là thứ *quan sát được công khai*: hàm đặc
 * quyền trong hợp đồng, mức độ tập trung người nắm giữ, thanh khoản bị rút,
 * tuổi tên miền, số kênh quảng bá. Không có trường nào nói "đây là lừa đảo" —
 * đó là kết luận của người điều tra, không phải của bảng dữ liệu.
 */

const STATUS_COLOR: Record<string, string> = {
  monitoring: C.info,
  flagged: C.warn,
  investigating: C.risk,
  cleared: C.ok,
};

const STATUS_LABEL: Record<string, string> = {
  monitoring: "Đang theo dõi",
  flagged: "Đã gắn cờ",
  investigating: "Đang điều tra",
  cleared: "Đã loại trừ",
};

/** Hàm đặc quyền cho phép người phát hành đơn phương tác động tới người nắm giữ. */
const DANGEROUS_FUNCTIONS = new Set(["mint", "pause", "blacklist", "setFee", "setTax", "upgradeTo"]);

export function ProjectsPage() {
  const data = useApi(() => api.projects(), [], "projects");
  const projects = data.data ?? [];

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Rủi ro dự án"
        meta="Đặc trưng quan sát công khai của dự án token — dùng để xếp thứ tự rà soát, không phải để kết luận"
      />

      {data.loading && <Skeleton rows={4} />}
      {data.error && <ErrorState detail={data.error} onRetry={data.reload} />}
      {!data.loading && !data.error && !projects.length && (
        <Empty
          text="Bộ dữ liệu IBM AML không cung cấp dữ liệu dự án token"
          hint="Cần nguồn hợp đồng, holder và thanh khoản on-chain riêng; hệ thống không suy diễn từ giao dịch ngân hàng."
        />
      )}

      <div className="flex flex-col gap-3">
        {projects.map((p) => {
          const risky = p.privileged_functions.filter((f) => DANGEROUS_FUNCTIONS.has(f));
          return (
            <Panel key={p.id} className="p-0">
              <div className="flex flex-wrap items-start gap-3 border-b border-line-soft px-3.5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-2xl font-semibold">{p.name}</span>
                    <span className="rounded-[5px] border border-line-strong px-1.5 font-mono text-2xs text-ink-soft">
                      {p.symbol}
                    </span>
                    <Chip color={STATUS_COLOR[p.status] ?? C.inkSoft}>{STATUS_LABEL[p.status] ?? p.status}</Chip>
                    <span className="text-2xs uppercase tracking-[0.1em] text-ink-low">{p.chain}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 font-mono text-2xs text-ink-low">
                    <span title={p.contract_address}>hợp đồng {shortAddr(p.contract_address, 10, 6)}</span>
                    <span title={p.deployer_address}>người triển khai {shortAddr(p.deployer_address, 10, 6)}</span>
                    <span>phát hành {formatDate(p.launched_at)}</span>
                  </div>
                </div>
                <div className="flex-none">
                  <div className="mb-1 text-right text-2xs text-ink-low">Điểm rủi ro</div>
                  <RiskScore score={p.risk_score} width={90} />
                </div>
              </div>

              <div className="grid gap-3 px-3.5 py-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
                <Metric
                  label="Tập trung người nắm giữ"
                  value={p.holder_gini != null ? p.holder_gini.toFixed(3) : "—"}
                  bar={p.holder_gini != null ? p.holder_gini * 100 : null}
                  // Gini càng gần 1 nghĩa là một nhóm rất nhỏ nắm gần hết nguồn cung.
                  hint="Hệ số Gini — càng gần 1 càng tập trung"
                  color={p.holder_gini != null && p.holder_gini > 0.85 ? C.risk : C.warn}
                />
                <Metric
                  label="Thanh khoản bị rút"
                  value={p.liquidity_removed_pct != null ? `${p.liquidity_removed_pct.toFixed(1)}%` : "—"}
                  bar={p.liquidity_removed_pct}
                  hint={`Còn lại ${usd(p.liquidity_usd)}`}
                  color={(p.liquidity_removed_pct ?? 0) > 80 ? C.risk : C.warn}
                />
                <Metric
                  label="Tuổi tên miền"
                  value={p.domain_age_days != null ? `${p.domain_age_days} ngày` : "—"}
                  bar={p.domain_age_days != null ? Math.min(100, (p.domain_age_days / 365) * 100) : null}
                  hint="Dưới 90 ngày là dấu hiệu cần chú ý"
                  color={(p.domain_age_days ?? 999) < 90 ? C.warn : C.ok}
                />
                <Metric
                  label="Kênh quảng bá"
                  value={String(p.kol_channels)}
                  bar={Math.min(100, p.kol_channels * 10)}
                  hint="Số kênh người có sức ảnh hưởng/tiếp thị liên kết quan sát được"
                  color={p.kol_channels >= 5 ? C.warn : C.info}
                />
              </div>

              <div className="border-t border-line-soft px-3.5 py-3">
                <div className="fc-eyebrow mb-2">Hàm đặc quyền trong hợp đồng</div>
                <div className="flex flex-wrap gap-1.5">
                  {p.privileged_functions.length === 0 && (
                    <span className="text-xs text-ink-low">Không phát hiện hàm đặc quyền nào</span>
                  )}
                  {p.privileged_functions.map((f) => (
                    <Chip key={f} color={DANGEROUS_FUNCTIONS.has(f) ? C.risk : C.inkSoft}>
                      {f}()
                    </Chip>
                  ))}
                </div>
                {risky.length > 0 && (
                  <p className="mt-2 text-2xs leading-relaxed text-ink-low">
                    {risky.length} hàm cho phép người phát hành đơn phương thay đổi điều kiện nắm giữ của người khác.
                    Đây là đặc trưng có thật trong mã hợp đồng, không phải suy đoán về ý định — nhưng nó cũng tồn tại
                    hợp lệ ở nhiều dự án có quản trị minh bạch.
                  </p>
                )}
              </div>
            </Panel>
          );
        })}
      </div>

      {projects.length > 0 && (
        <Panel title="Cách đọc màn hình này">
          <p className="text-xs leading-relaxed text-ink-soft">
            Các chỉ số ở đây dùng để <b className="text-ink-mid">xếp thứ tự rà soát</b>, không phải để kết luận. Một dự
            án có Gini cao, thanh khoản bị rút và tên miền mới vẫn có thể là một dự án hợp pháp gặp sự cố; ngược lại,
            một dự án chỉ số đẹp vẫn có thể có vấn đề ở phần không quan sát được.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-ink-low">
            Kết luận về hành vi cần bằng chứng ở tầng điều tra — thiết bị, mã nguồn, tài khoản quản trị, phản hồi của
            sàn — và thẩm quyền tương ứng. Xem nhật ký mở quyền ở màn hình Chất lượng dữ liệu.
          </p>
        </Panel>
      )}
    </PageShell>
  );
}

function Metric({
  label,
  value,
  bar,
  hint,
  color,
}: {
  label: string;
  value: string;
  bar: number | null;
  hint: string;
  color: string;
}) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-[0.06em] text-ink-low">{label}</div>
      <div className="tabular my-1 font-mono text-2xl font-semibold" style={{ color }}>
        {value}
      </div>
      {bar != null && <ProgressBar value={bar} color={color} />}
      <div className="mt-1 text-3xs text-ink-dim">{hint}</div>
    </div>
  );
}
