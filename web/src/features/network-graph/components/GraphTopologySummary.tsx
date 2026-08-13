import { usd } from "../../../api/fcFormat";
import { Eyebrow, StatTile } from "../../../components/fc/primitives";
import { C } from "../../../design/palette";
import type { GraphModel, MoneyPath, RenderGraph } from "../types/graph.types";
import type { InvestigationHealth } from "../utils/evidenceGaps";

interface Props {
  model: GraphModel;
  graph: RenderGraph;
  paths: MoneyPath[];
  cycles: string[][];
  health: InvestigationHealth;
  onOpenQuestions: () => void;
}

/**
 * Trạng thái A của panel phải: chưa chọn gì.
 *
 * Bản cũ để trống chỗ này với một câu "hãy nhấp vào node" — lãng phí cột rộng
 * nhất màn hình. Giờ nó trả lời ngay câu hỏi đầu tiên của analyst: vụ này to
 * cỡ nào, tiền bao nhiêu, có bao nhiêu đường đáng lần theo.
 */
export function GraphTopologySummary({ model, graph, paths, cycles, health, onOpenQuestions }: Props) {
  const mule = model.clusters.find((c) => c.id === "CL-MULE");
  const deviceCluster = model.clusters.find((c) => c.id === "CL-DEVICE");
  const offRamp = model.nodes.filter((n) => n.stage === "gateway" || n.stage === "conversion").length;
  const highRisk = model.nodes.filter((n) => n.risk >= 80 && !n.negative).length;
  const inferred = model.edges.filter((e) => e.inferred).length;

  const tiles: { label: string; value: string; color?: string }[] = [
    { label: "Đỉnh đang vẽ", value: String(graph.nodes.length) },
    { label: "Cạnh đang vẽ", value: String(graph.edges.length) },
    { label: "Đường tiền", value: String(paths.length), color: C.info },
    { label: "Chu trình", value: String(cycles.length), color: cycles.length ? C.warn : C.inkLow },
    { label: "Rủi ro ≥ 80", value: String(highRisk), color: C.risk },
    { label: "Cạnh suy luận", value: String(inferred), color: C.agent },
  ];

  return (
    <div className="animate-up">
      <Eyebrow className="mb-2">Tóm tắt cấu trúc mạng</Eyebrow>
      <div className="grid grid-cols-2 gap-[7px]">
        {tiles.map((t) => (
          <StatTile key={t.label} label={t.label} value={t.value} valueColor={t.color ?? C.inkHi} />
        ))}
      </div>

      {/* Sức khoẻ điều tra.
          Đặt ngay dưới các chỉ số quy mô có chủ đích: biết mạng lưới to cỡ nào
          là chưa đủ, phải biết bao nhiêu phần trong đó đứng vững được. */}
      <div className="mt-3 rounded-control border border-line bg-sunken px-2.5 py-2">
        <div className="flex items-baseline gap-2">
          <span className="text-2xs text-ink-low">Độ phủ bằng chứng</span>
          <b
            className="tabular ml-auto font-mono text-lg"
            style={{ color: health.coveragePct >= 80 ? C.ok : health.coveragePct >= 60 ? C.warn : C.risk }}
          >
            {health.coveragePct}%
          </b>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-app">
          <div
            className="h-full rounded-full transition-[width] duration-300"
            style={{
              width: `${health.coveragePct}%`,
              background: health.coveragePct >= 80 ? C.ok : health.coveragePct >= 60 ? C.warn : C.risk,
            }}
          />
        </div>

        <div className="mt-2 grid grid-cols-3 gap-1.5">
          <button
            type="button"
            onClick={onOpenQuestions}
            className="rounded-control bg-app px-1.5 py-1 text-left transition-colors hover:bg-elev"
          >
            <span className="block font-mono text-sm text-warn-soft">{health.openQuestions}</span>
            <span className="block text-3xs leading-tight text-ink-dim">Câu hỏi mở</span>
          </button>
          <div className="rounded-control bg-app px-1.5 py-1">
            <span className="block font-mono text-sm text-ink-soft">{health.missingLinks}</span>
            <span className="block text-3xs leading-tight text-ink-dim">Thiếu liên kết</span>
          </div>
          <div className="rounded-control bg-app px-1.5 py-1">
            <span className="block font-mono text-sm text-ok-soft">{health.alternatives}</span>
            <span className="block text-3xs leading-tight text-ink-dim">Đối chứng</span>
          </div>
        </div>
      </div>

      <dl className="mt-3 flex flex-col gap-1.5 text-xs">
        <div className="flex gap-2">
          <dt className="w-32 flex-none text-ink-low">Tổng dòng tiền</dt>
          <dd className="tabular font-mono text-ink-hi">{usd(model.totalFlowUsd)}</dd>
        </div>
        {mule && (
          <div className="flex gap-2">
            <dt className="w-32 flex-none text-ink-low">Tài khoản trung chuyển</dt>
            <dd className="text-ink-mid">{mule.memberIds.length}</dd>
          </div>
        )}
        {deviceCluster && (
          <div className="flex gap-2">
            <dt className="w-32 flex-none text-ink-low">Thiết bị dùng chung</dt>
            <dd className="text-ink-mid">{deviceCluster.memberIds.length}</dd>
          </div>
        )}
        <div className="flex gap-2">
          <dt className="w-32 flex-none text-ink-low">Điểm đổi tiền</dt>
          <dd className="text-ink-mid">{offRamp}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-32 flex-none text-ink-low">Đối chứng hợp pháp</dt>
          <dd className="text-ok-soft">{model.nodes.filter((n) => n.negative).length}</dd>
        </div>
      </dl>
    </div>
  );
}
