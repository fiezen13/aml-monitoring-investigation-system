import { useMemo } from "react";

import { usd } from "../../../api/fcFormat";
import { Chip, StatTile } from "../../../components/fc/primitives";
import { C, riskColor, riskLabel } from "../../../design/palette";
import type { InspectorTab } from "../stores/graph.store";
import type { GNode, GraphModel } from "../types/graph.types";
import { STAGE_LABEL } from "../types/graph.types";
import { LAYER_LABEL, typeStyle } from "../utils/graphStyles";

const TABS: [InspectorTab, string][] = [
  ["overview", "Tổng quan"],
  ["transactions", "Giao dịch"],
  ["relationships", "Quan hệ"],
  ["evidence", "Bằng chứng"],
  ["model", "Mô hình"],
];

interface Props {
  node: GNode;
  model: GraphModel;
  tab: InspectorTab;
  onTab: (t: InspectorTab) => void;
  onClose: () => void;
  onExpand: () => void;
  onFindPath: () => void;
  onIsolate: () => void;
}

export function NodeInspector({ node, model, tab, onTab, onClose, onExpand, onFindPath, onIsolate }: Props) {
  const st = typeStyle(node.type);

  const related = useMemo(() => {
    const inbound = model.edges.filter((e) => e.t === node.id);
    const outbound = model.edges.filter((e) => e.s === node.id);
    return { inbound, outbound, all: [...inbound, ...outbound] };
  }, [model.edges, node.id]);

  const txns = related.all.filter((e) => e.money);
  const inferredEdges = related.all.filter((e) => e.inferred);

  return (
    <div className="animate-up">
      <div className="flex items-start gap-2">
        <Chip color={st.color}>{st.name}</Chip>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xl font-semibold text-ink-hi">{node.label}</div>
          <div className="mt-0.5 font-mono text-2xs text-ink-low">{node.sub}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng inspector"
          className="flex-none text-ink-low hover:text-ink-hi"
        >
          ✕
        </button>
      </div>

      {node.negative && (
        <div className="mt-2.5 rounded-control border border-ok/30 bg-ok/10 px-3 py-2 text-xs leading-relaxed text-ok-soft">
          Đây là <b>đối chứng hợp pháp</b> — thực thể hợp pháp cố ý đưa vào để đo tỷ lệ dương tính giả. Mô hình gắn cờ
          nó là một lỗi cần ghi nhận, không phải một phát hiện.
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-[7px]">
        <StatTile label="Điểm rủi ro" value={String(node.risk)} valueColor={riskColor(node.risk)} />
        <StatTile label="Mức độ" value={riskLabel(node.risk)} valueColor={riskColor(node.risk)} />
        <StatTile label="Tiền vào" value={node.inUsd ? usd(node.inUsd) : "—"} />
        <StatTile label="Tiền ra" value={node.outUsd ? usd(node.outUsd) : "—"} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={onExpand}
          className="rounded-control border border-line bg-sunken px-2.5 py-1 text-2xs text-ink-soft transition-colors hover:bg-elev hover:text-ink-mid"
        >
          Mở rộng lân cận
        </button>
        <button
          type="button"
          onClick={onFindPath}
          className="rounded-control border border-primary-line bg-primary-soft px-2.5 py-1 text-2xs text-primary transition-colors hover:bg-elev"
        >
          Tìm đường tiền
        </button>
        <button
          type="button"
          onClick={onIsolate}
          className="rounded-control border border-line bg-sunken px-2.5 py-1 text-2xs text-ink-soft transition-colors hover:bg-elev hover:text-ink-mid"
        >
          Cô lập
        </button>
      </div>

      <div className="mt-3 flex gap-0.5 border-b border-line">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => onTab(key)}
            aria-selected={tab === key}
            className={[
              "border-b-2 px-2 py-1.5 text-2xs transition-colors",
              tab === key
                ? "border-primary text-primary"
                : "border-transparent text-ink-low hover:text-ink-mid",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-3">
        {tab === "overview" && (
          <dl className="flex flex-col gap-1.5 text-xs">
            <Row label="Vai trò" value={node.role} />
            <Row label="Chặng" value={STAGE_LABEL[node.stage]} />
            <Row label="Mức ưu tiên" value={`Tier ${node.tier}`} />
            <Row label="Trung tâm" value={node.hub ?? "—"} />
            <Row label="Bậc đỉnh" value={String(node.degree)} />
            <Row label="Xuất hiện" value={node.first} />
            <Row label="Gần nhất" value={node.last} />
          </dl>
        )}

        {tab === "transactions" &&
          (txns.length ? (
            <ul className="flex flex-col gap-1">
              {txns.slice(0, 40).map((e) => {
                const other = e.s === node.id ? model.byId[e.t] : model.byId[e.s];
                const out = e.s === node.id;
                return (
                  <li
                    key={e.id}
                    className="flex items-center gap-2 rounded-control border border-line bg-sunken px-2 py-1.5 text-2xs"
                  >
                    <span className={out ? "text-risk-soft" : "text-ok"}>{out ? "↗" : "↙"}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-mid">{other?.label ?? "—"}</span>
                    <span className="tabular font-mono text-ink-soft">{e.amt != null ? usd(e.amt) : "—"}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Empty>Không có giao dịch tiền nối tới đỉnh này.</Empty>
          ))}

        {tab === "relationships" &&
          (related.all.length ? (
            <ul className="flex flex-col gap-1">
              {related.all.slice(0, 40).map((e) => {
                const other = e.s === node.id ? model.byId[e.t] : model.byId[e.s];
                return (
                  <li
                    key={e.id}
                    className="flex items-center gap-2 rounded-control border border-line bg-sunken px-2 py-1.5 text-2xs"
                  >
                    <span className="text-ink-dim">{LAYER_LABEL[e.layer]}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-mid">{other?.label ?? "—"}</span>
                    {e.inferred && <span className="font-mono text-agent-soft">suy luận</span>}
                  </li>
                );
              })}
            </ul>
          ) : (
            <Empty>Đỉnh này chưa có quan hệ nào trong mô hình.</Empty>
          ))}

        {tab === "evidence" &&
          (inferredEdges.length ? (
            <div className="flex flex-col gap-2">
              {inferredEdges.map((e) => (
                <div key={e.id} className="rounded-control border border-agent/30 bg-agent/10 px-2.5 py-2">
                  <div className="mb-1 flex items-baseline gap-2">
                    <span className="text-3xs uppercase tracking-[0.08em] text-agent-soft">Cơ sở suy luận</span>
                    <b className="tabular font-mono text-sm" style={{ color: (e.conf ?? 0) >= 0.7 ? C.ok : C.warn }}>
                      {e.conf != null ? e.conf.toFixed(2) : "—"}
                    </b>
                  </div>
                  <p className="text-xs leading-relaxed text-ink-mid">{e.logic ?? "—"}</p>
                </div>
              ))}
            </div>
          ) : (
            <Empty>Mọi quan hệ của đỉnh này đều là quan sát trực tiếp — không có suy luận cần phản biện.</Empty>
          ))}

        {tab === "model" && (
          <div className="flex flex-col gap-2 text-xs">
            <dl className="flex flex-col gap-1.5">
              <Row label="Tier thị giác" value={`Tier ${node.tier} · ${node.band}`} />
              <Row label="Cụm" value={node.clusterId ?? "đứng riêng"} />
              <Row label="Mốc chuẩn hoá" value={node.t.toFixed(3)} />
            </dl>
            <p className="rounded-control border border-line bg-sunken px-2.5 py-2 text-3xs leading-relaxed text-ink-low">
              Điểm rủi ro do lớp Risk Fusion chấm trên bằng chứng quan sát được. Vai trò và chặng ở đây là suy luận của
              giao diện để xếp bố cục — chúng không phải kết luận điều tra và không được trích vào hồ sơ.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-28 flex-none text-ink-low">{label}</dt>
      <dd className="min-w-0 flex-1 break-words text-ink-mid">{value}</dd>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs leading-relaxed text-ink-low">{children}</p>;
}
