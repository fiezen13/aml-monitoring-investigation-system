import { conf as confFmt, usd } from "../../../api/fcFormat";
import { Chip, StatTile } from "../../../components/fc/primitives";
import { C } from "../../../design/palette";
import type { GraphModel, RenderEdge } from "../types/graph.types";
import { LAYER_LABEL } from "../utils/graphStyles";

interface Props {
  edge: RenderEdge;
  model: GraphModel;
  onClose: () => void;
}

/**
 * Inspector cho cạnh.
 *
 * Phần quan trọng nhất vẫn giữ nguyên tinh thần bản cũ: nói rõ đây là *quan
 * sát* hay *suy luận*, và nếu suy luận thì suy từ đâu, tin được tới đâu. Không
 * có phần này thì đồ thị chỉ là hình đẹp.
 */
export function EdgeInspector({ edge, model, onClose }: Props) {
  const a = model.byId[edge.s];
  const b = model.byId[edge.t];
  const low = (edge.conf ?? 1) < 0.7;

  return (
    <div className="animate-up">
      <div className="flex items-center gap-2">
        <Chip color={edge.inferred ? C.agent : C.info}>{edge.inferred ? "SUY LUẬN" : "QUAN SÁT"}</Chip>
        <div className="flex-1 text-base font-semibold text-ink-hi">{LAYER_LABEL[edge.layer]}</div>
        <button type="button" onClick={onClose} aria-label="Đóng inspector" className="text-ink-low hover:text-ink-hi">
          ✕
        </button>
      </div>

      <div className="mt-2 text-xs text-ink-mid">
        <span className="text-ink-soft">{a?.label ?? edge.s}</span>
        <span className="mx-1.5 text-ink-low">→</span>
        <span className="text-ink-soft">{b?.label ?? edge.t}</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-[7px]">
        {edge.amt != null && <StatTile label="Giá trị" value={usd(edge.amt)} />}
        {edge.count > 1 && <StatTile label="Số quan hệ gộp" value={String(edge.count)} valueColor={C.primary} />}
      </div>

      {/* Chứng cứ giao dịch. Đây là chỗ trả lời "quan hệ này dựa trên cái gì" —
          bản cũ chỉ có một con số USD không nói được nó gồm mấy lần chuyển. */}
      <div className="mt-3 rounded-control bg-sunken px-2.5 py-2">
        <div className="fc-eyebrow mb-1.5">Chứng cứ giao dịch</div>
        {edge.txCount > 0 ? (
          <>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="tabular font-mono text-2xl font-semibold text-ink-hi">{edge.txCount}</span>
              <span className="text-2xs text-ink-low">giao dịch</span>
              {Object.entries(edge.amountsByCurrency).map(([ccy, amount]) => (
                <span key={ccy} className="tabular font-mono text-2xs text-ink-soft">
                  {ccy === "USD" ? usd(amount) : `${amount.toLocaleString("vi-VN")} ${ccy}`}
                </span>
              ))}
            </div>
            <p className="mt-1.5 text-3xs leading-relaxed text-ink-low">
              Mở tab <b className="text-ink-soft">Giao dịch</b> ở panel dưới để xem từng lần chuyển khoản.
            </p>
          </>
        ) : (
          // §41: nói thẳng, không bịa một con số nào.
          <p className="text-2xs leading-relaxed text-ink-low">
            Không có bằng chứng giao dịch. Quan hệ sở hữu, thiết bị dùng chung và chuyển trên chuỗi không sinh ra
            chuyển khoản ngân hàng nào để đối chiếu.
          </p>
        )}
      </div>

      {edge.count > 1 && (
        <p className="mt-2 rounded-control border border-line bg-sunken px-2.5 py-2 text-3xs leading-relaxed text-ink-low">
          Cạnh này là kết quả gộp vì một trong hai đầu đang là cụm thu gọn. Mở cụm ra để thấy từng quan hệ riêng.
        </p>
      )}

      {edge.inferred ? (
        <div className="mt-3 rounded-control border border-agent/30 bg-agent/10 px-3 py-2.5">
          <div className="mb-1.5 text-3xs uppercase tracking-[0.08em] text-agent-soft">Cơ sở suy luận</div>
          <div className="mb-2 flex items-baseline gap-2">
            <span className="text-2xs text-ink-low">Độ tin cậy</span>
            <b
              className="tabular font-mono text-2xl"
              style={{ color: (edge.conf ?? 0) >= 0.75 ? C.ok : (edge.conf ?? 0) >= 0.6 ? C.warn : C.risk }}
            >
              {confFmt(edge.conf ?? undefined)}
            </b>
          </div>
          <p className="text-xs leading-relaxed text-ink-mid">{edge.ref?.logic ?? "—"}</p>
          {low && (
            <p className="mt-2 text-2xs leading-relaxed text-warn-soft">
              Độ tin cậy dưới 0.70 — quan hệ này một mình không đủ làm căn cứ. Cần bằng chứng độc lập trước khi đưa vào
              lập luận của hồ sơ.
            </p>
          )}
        </div>
      ) : (
        <div className="mt-3 rounded-control border border-info/30 bg-info/10 px-3 py-2.5 text-xs leading-relaxed text-ink-mid">
          Quan hệ này được quan sát trực tiếp từ hệ thống nguồn, không phải kết quả suy luận của mô hình.
        </div>
      )}
    </div>
  );
}
