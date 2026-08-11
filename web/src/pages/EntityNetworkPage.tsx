import { useMemo, useState } from "react";

import { api } from "../api/client";
import { conf, usd } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { NetGraph, type GraphEdge, type GraphNode } from "../components/fc/NetGraph";
import { Chip, Eyebrow, PulseDot, StatTile } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * Network Graph — đồ thị thực thể của toàn bộ mạng lưới mô phỏng.
 *
 * Khác với `NetworkPage` (đồ thị gọn theo một vụ việc, dựng bằng React Flow),
 * màn hình này vẽ toàn bộ mạng lưới bằng engine canvas của prototype vì số
 * đỉnh lớn hơn nhiều và cần layout lực chạy liên tục.
 *
 * Cột phải là phần quan trọng nhất: khi chọn một cạnh, nó nói rõ đó là *quan
 * sát trực tiếp* hay *suy luận*, và nếu là suy luận thì suy từ đâu, tin được
 * tới mức nào. Không có phần này thì đồ thị chỉ là hình đẹp — analyst không
 * phản biện được điều gì.
 */

const NODE_TYPES = [
  ["account", "Tài khoản"],
  ["person", "Cá nhân"],
  ["wallet", "Ví"],
  ["device", "Thiết bị"],
  ["platform", "Nền tảng"],
  ["organisation", "Tổ chức"],
  ["vasp", "VASP"],
  ["project", "Dự án"],
] as const;

const EDGE_KINDS = [
  ["transfer", "Chuyển tiền"],
  ["owns", "Sở hữu"],
  ["device", "Dùng chung thiết bị"],
  ["control", "Điều phối"],
  ["swap", "Hoán đổi"],
  ["bridge", "Bắc cầu"],
] as const;

const EDGE_LABEL: Record<string, string> = Object.fromEntries(EDGE_KINDS);

type SelectedEdge = GraphEdge & { sLabel?: string; tLabel?: string };

export function EntityNetworkPage() {
  const graph = useApi(() => api.entityGraph(600), []);

  const [types, setTypes] = useState<Record<string, boolean>>(
    Object.fromEntries(NODE_TYPES.map(([t]) => [t, true])),
  );
  const [kinds, setKinds] = useState<Record<string, boolean>>(
    Object.fromEntries(EDGE_KINDS.map(([k]) => [k, true])),
  );
  const [riskMin, setRiskMin] = useState(0);
  const [timeT, setTimeT] = useState(100);
  const [selNode, setSelNode] = useState<GraphNode | null>(null);
  const [selEdge, setSelEdge] = useState<SelectedEdge | null>(null);

  // Chuẩn hoá mốc thời gian về 0→1: engine chỉ hiểu vị trí tương đối trong cửa
  // sổ mô phỏng, không hiểu ngày tháng.
  const data = useMemo(() => {
    const g = graph.data;
    if (!g?.nodes.length) return null;
    const times = g.nodes.map((n) => new Date(n.first).getTime());
    const min = Math.min(...times);
    const span = Math.max(1, Math.max(...times) - min);
    return {
      nodes: g.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        label: n.label,
        sub: n.sub,
        risk: n.risk,
        t: (new Date(n.first).getTime() - min) / span,
        first: formatDateTime(n.first),
        last: formatDateTime(n.last),
        negative: n.negative,
      })),
      edges: g.edges.map((e) => ({
        s: e.s,
        t: e.t,
        kind: e.kind,
        label: e.label,
        amt: e.amt ?? undefined,
        time: (new Date(e.known_from).getTime() - min) / span,
        inferred: e.inferred,
        conf: e.conf ?? undefined,
        logic: e.logic ?? undefined,
      })),
    };
  }, [graph.data]);

  const stats = useMemo(() => {
    const g = graph.data;
    if (!g) return [];
    const inferred = g.edges.filter((e) => e.inferred);
    return [
      { l: "Thực thể", v: String(g.nodes.length), c: C.inkHi },
      { l: "Quan hệ", v: String(g.edges.length), c: C.inkHi },
      { l: "Cạnh suy luận", v: String(inferred.length), c: C.agent },
      { l: "Suy luận yếu", v: String(inferred.filter((e) => (e.conf ?? 1) < 0.7).length), c: C.warn },
      { l: "Rủi ro ≥ 80", v: String(g.nodes.filter((n) => n.risk >= 80).length), c: C.risk },
      { l: "Hard negative", v: String(g.nodes.filter((n) => n.negative).length), c: C.ok },
    ];
  }, [graph.data]);

  return (
    <div className="flex h-full min-w-0 overflow-hidden">
      <aside className="flex min-w-[210px] flex-[0_2_260px] flex-col gap-3.5 overflow-y-auto border-r border-line bg-side p-3.5">
        <div>
          <Eyebrow className="mb-2">Tổng quan đồ thị</Eyebrow>
          <div className="grid grid-cols-2 gap-[7px]">
            {stats.map((s) => (
              <StatTile key={s.l} label={s.l} value={s.v} valueColor={s.c} />
            ))}
          </div>
        </div>

        <div>
          <Eyebrow className="mb-2">Loại thực thể</Eyebrow>
          <div className="flex flex-col gap-[3px]">
            {NODE_TYPES.map(([t, label]) => (
              <label
                key={t}
                className="flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-1 text-sm text-ink-mid transition-colors hover:bg-elev"
              >
                <input
                  type="checkbox"
                  checked={types[t]}
                  onChange={() => setTypes((s) => ({ ...s, [t]: !s[t] }))}
                  className="accent-primary"
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div>
          <Eyebrow className="mb-2">Loại quan hệ</Eyebrow>
          <div className="flex flex-col gap-[3px]">
            {EDGE_KINDS.map(([k, label]) => (
              <label
                key={k}
                className="flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-1 text-sm text-ink-mid transition-colors hover:bg-elev"
              >
                <input
                  type="checkbox"
                  checked={kinds[k]}
                  onChange={() => setKinds((s) => ({ ...s, [k]: !s[k] }))}
                  className="accent-primary"
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div>
          <Eyebrow className="mb-2">Điểm rủi ro tối thiểu · {riskMin}</Eyebrow>
          <input
            type="range"
            min={0}
            max={100}
            value={riskMin}
            onChange={(e) => setRiskMin(Number(e.target.value))}
            aria-label="Điểm rủi ro tối thiểu"
            className="w-full accent-primary"
          />
        </div>

        <div>
          <Eyebrow className="mb-2">Thời gian · {timeT === 100 ? "toàn bộ" : `${timeT}%`}</Eyebrow>
          <input
            type="range"
            min={0}
            max={100}
            value={timeT}
            onChange={(e) => setTimeT(Number(e.target.value))}
            aria-label="Thanh trượt thời gian"
            className="w-full accent-agent"
          />
          <p className="mt-1 text-3xs leading-relaxed text-ink-dim">
            Kéo về trái để xem mạng lưới hình thành dần — thứ tự xuất hiện thường nói nhiều hơn hình dạng cuối cùng.
          </p>
        </div>
      </aside>

      <div className="relative min-w-[360px] flex-1 bg-app">
        {graph.loading && (
          <div className="absolute inset-0 grid place-items-center text-sm text-ink-low">Đang dựng đồ thị…</div>
        )}
        {!graph.loading && !data && (
          <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-ink-low">
            <div>
              Chưa có dữ liệu đồ thị.
              <br />
              <span className="text-2xs text-ink-dim">Chạy scripts/abm_generate.py để sinh mạng lưới mô phỏng.</span>
            </div>
          </div>
        )}
        <NetGraph
          data={data}
          filterTypes={types}
          filterEdges={kinds}
          riskMin={riskMin}
          timeT={timeT / 100}
          onSelectNode={(n) => {
            setSelNode(n);
            setSelEdge(null);
          }}
          onSelectEdge={(e) => {
            setSelEdge(e as SelectedEdge | null);
            setSelNode(null);
          }}
        />

        <div className="absolute left-3.5 top-3 flex items-center gap-2 rounded-chip border border-line bg-side/85 px-3 py-1 text-2xs backdrop-blur">
          <PulseDot color={C.primary} />
          <span className="font-mono tracking-[0.08em] text-primary">
            {data ? `${data.nodes.length} thực thể · ${data.edges.length} quan hệ` : "—"}
          </span>
        </div>
      </div>

      <aside className="flex min-h-0 min-w-[240px] flex-[0_3_330px] flex-col overflow-y-auto border-l border-line bg-side p-3.5">
        {!selNode && !selEdge && (
          <div className="text-sm leading-relaxed text-ink-low">
            <Eyebrow className="mb-2">Inspector</Eyebrow>
            Nhấp vào một thực thể hoặc một quan hệ trên đồ thị để xem chi tiết.
            <p className="mt-3 text-xs leading-relaxed text-ink-dim">
              Quan hệ vẽ nét đứt là quan hệ do mô hình <b className="text-ink-soft">suy ra</b>, không phải quan sát trực
              tiếp. Mỗi cạnh như vậy đều kèm độ tin cậy và diễn giải — đọc chúng trước khi dùng làm căn cứ.
            </p>
          </div>
        )}

        {selNode && (
          <div className="animate-up">
            <div className="flex items-center gap-2">
              <Chip color={C.primary}>{selNode.type}</Chip>
              <div className="truncate-1 flex-1 text-xl font-semibold">{selNode.label}</div>
              <button
                type="button"
                onClick={() => setSelNode(null)}
                aria-label="Đóng inspector"
                className="text-ink-low hover:text-ink-hi"
              >
                ✕
              </button>
            </div>
            <div className="mt-0.5 font-mono text-2xs text-ink-low">{selNode.sub}</div>

            {selNode.negative && (
              <div className="mt-2.5 rounded-control border border-ok/30 bg-ok/10 px-3 py-2 text-xs leading-relaxed text-ok-soft">
                Đây là <b>hard negative</b> — thực thể hợp pháp cố ý đưa vào để đo tỷ lệ dương tính giả. Mô hình gắn cờ
                nó là một lỗi cần ghi nhận, không phải một phát hiện.
              </div>
            )}

            <div className="mt-3 grid grid-cols-2 gap-[7px]">
              <StatTile
                label="Điểm rủi ro"
                value={String(selNode.risk)}
                valueColor={selNode.risk >= 80 ? C.risk : selNode.risk >= 60 ? C.warn : C.ok}
              />
              <StatTile label="Loại" value={selNode.type} />
            </div>
            <dl className="mt-3 flex flex-col gap-1.5 text-xs">
              <div className="flex gap-2">
                <dt className="w-24 flex-none text-ink-low">Xuất hiện</dt>
                <dd className="text-ink-mid">{selNode.first}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-24 flex-none text-ink-low">Gần nhất</dt>
                <dd className="text-ink-mid">{selNode.last}</dd>
              </div>
            </dl>
          </div>
        )}

        {selEdge && (
          <div className="animate-up">
            <div className="flex items-center gap-2">
              <Chip color={selEdge.inferred ? C.agent : C.info}>
                {selEdge.inferred ? "SUY LUẬN" : "QUAN SÁT"}
              </Chip>
              <div className="flex-1 text-base font-semibold">{EDGE_LABEL[selEdge.kind] ?? selEdge.kind}</div>
              <button
                type="button"
                onClick={() => setSelEdge(null)}
                aria-label="Đóng inspector"
                className="text-ink-low hover:text-ink-hi"
              >
                ✕
              </button>
            </div>

            {(selEdge.sLabel || selEdge.tLabel) && (
              <div className="mt-2 text-xs text-ink-mid">
                <span className="text-ink-soft">{selEdge.sLabel}</span>
                <span className="mx-1.5 text-ink-low">→</span>
                <span className="text-ink-soft">{selEdge.tLabel}</span>
              </div>
            )}

            {selEdge.amt != null && (
              <div className="mt-3">
                <StatTile label="Giá trị" value={usd(selEdge.amt)} />
              </div>
            )}

            {selEdge.inferred ? (
              <div className="mt-3 rounded-control border border-agent/30 bg-agent/10 px-3 py-2.5">
                <div className="fc-eyebrow mb-1.5" style={{ color: C.agentSoft }}>
                  Cơ sở suy luận
                </div>
                <div className="mb-2 flex items-baseline gap-2">
                  <span className="text-2xs text-ink-low">Độ tin cậy</span>
                  <b
                    className="tabular font-mono text-2xl"
                    style={{ color: (selEdge.conf ?? 0) >= 0.75 ? C.ok : (selEdge.conf ?? 0) >= 0.6 ? C.warn : C.risk }}
                  >
                    {conf(selEdge.conf)}
                  </b>
                </div>
                <p className="text-xs leading-relaxed text-ink-mid">{selEdge.logic}</p>
                {(selEdge.conf ?? 0) < 0.7 && (
                  <p className="mt-2 text-2xs leading-relaxed text-warn-soft">
                    Độ tin cậy dưới 0.70 — quan hệ này một mình không đủ làm căn cứ. Cần bằng chứng độc lập trước khi
                    đưa vào lập luận của hồ sơ.
                  </p>
                )}
              </div>
            ) : (
              <div className="mt-3 rounded-control border border-info/30 bg-info/10 px-3 py-2.5 text-xs leading-relaxed text-ink-mid">
                Quan hệ này được quan sát trực tiếp từ hệ thống nguồn, không phải kết quả suy luận của mô hình.
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
