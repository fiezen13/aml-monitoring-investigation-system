import { Eyebrow } from "../../../components/fc/primitives";
import type { GCluster, LayerKey } from "../types/graph.types";
import { LAYER_LABEL, LAYER_ORDER } from "../utils/graphStyles";

/** Kind cạnh gom theo lớp, dùng cho phần Advanced. */
const KINDS_BY_LAYER: Record<LayerKey, [string, string][]> = {
  money: [
    ["transfer", "Chuyển tiền"],
    ["p2p", "Mua bán P2P"],
    ["deposit", "Nạp tiền"],
    ["withdrawal", "Rút tiền"],
    ["crypto", "Chuyển ví"],
    ["swap", "Hoán đổi"],
    ["bridge", "Bắc cầu"],
  ],
  entity: [
    ["owns", "Sở hữu"],
    ["control", "Điều phối"],
    ["controls", "Điều khiển (suy luận)"],
    ["director", "Người đại diện"],
  ],
  device: [["device", "Thiết bị / IP dùng chung"]],
  alert: [["alert", "Gắn cảnh báo"]],
  case: [["member", "Thuộc vụ việc"]],
  negative: [],
};

interface Props {
  layers: Record<LayerKey, boolean>;
  mutedKinds: Record<string, boolean>;
  advancedOpen: boolean;
  clusters: GCluster[];
  collapsed: Record<string, boolean>;
  riskMin: number;
  minAmt: number;
  showAlternatives: boolean;
  onLayer: (layer: LayerKey, on: boolean) => void;
  onKind: (kind: string, muted: boolean) => void;
  onAdvanced: (on: boolean) => void;
  onToggleCluster: (id: string) => void;
  onRiskMin: (v: number) => void;
  onMinAmt: (v: number) => void;
  onAlternatives: (on: boolean) => void;
}

function Check({
  checked,
  label,
  hint,
  onChange,
}: {
  checked: boolean;
  label: string;
  hint?: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-1 text-sm text-ink-mid transition-colors hover:bg-elev">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-primary"
      />
      <span className="flex-1">{label}</span>
      {hint && <span className="font-mono text-3xs text-ink-dim">{hint}</span>}
    </label>
  );
}

/**
 * Panel trái rút gọn.
 *
 * Bản cũ đổ thẳng 14 checkbox loại quan hệ ra màn hình đầu tiên. Ở đây chỉ còn
 * sáu lớp — đúng mức trừu tượng mà analyst nghĩ — còn danh sách kind đầy đủ
 * nằm sau "Bộ lọc nâng cao" cho người thật sự cần.
 */
export function GraphLayerPanel({
  layers,
  mutedKinds,
  advancedOpen,
  clusters,
  collapsed,
  riskMin,
  minAmt,
  showAlternatives,
  onLayer,
  onKind,
  onAdvanced,
  onToggleCluster,
  onRiskMin,
  onMinAmt,
  onAlternatives,
}: Props) {
  return (
    <>
      <div>
        <Eyebrow className="mb-2">Lớp hiển thị</Eyebrow>
        <div className="flex flex-col gap-[2px]">
          {LAYER_ORDER.map((key) => (
            <Check
              key={key}
              checked={layers[key]}
              label={LAYER_LABEL[key]}
              onChange={(v) => onLayer(key, v)}
            />
          ))}
        </div>
        <label className="mt-1 flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-1 text-sm text-ok-soft transition-colors hover:bg-elev">
          <input
            type="checkbox"
            checked={showAlternatives}
            onChange={(e) => onAlternatives(e.target.checked)}
            className="accent-primary"
          />
          Làm nổi đối chứng
        </label>
      </div>

      {clusters.length > 0 && (
        <div>
          <Eyebrow className="mb-2">Cụm</Eyebrow>
          <div className="flex max-h-[188px] flex-col gap-1 overflow-y-auto pr-0.5">
            {clusters.map((c) => {
              const isCollapsed = collapsed[c.id] !== false;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onToggleCluster(c.id)}
                  className="flex items-center gap-2 rounded-control border border-line bg-sunken px-2 py-1.5 text-left text-2xs transition-colors hover:bg-elev"
                >
                  <span className="text-ink-dim">{isCollapsed ? "▸" : "▾"}</span>
                  <span className="flex-1 truncate text-ink-mid">{c.label}</span>
                  <span className="font-mono text-ink-low">×{c.memberIds.length}</span>
                  <span
                    className="font-mono"
                    style={{ color: c.risk >= 80 ? "#FF4D61" : c.risk >= 60 ? "#F5A524" : "#2DD4A7" }}
                  >
                    {c.risk}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <Eyebrow className="mb-2">Điểm rủi ro tối thiểu · {riskMin}</Eyebrow>
        <input
          type="range"
          min={0}
          max={100}
          value={riskMin}
          onChange={(e) => onRiskMin(Number(e.target.value))}
          aria-label="Điểm rủi ro tối thiểu"
          className="w-full accent-primary"
        />
      </div>

      <div>
        <button
          type="button"
          onClick={() => onAdvanced(!advancedOpen)}
          aria-expanded={advancedOpen}
          className="flex w-full items-center gap-1.5 text-left text-2xs font-semibold uppercase tracking-[0.08em] text-ink-dim transition-colors hover:text-ink-soft"
        >
          <span>{advancedOpen ? "▾" : "▸"}</span>
          Bộ lọc nâng cao
        </button>

        {advancedOpen && (
          <div className="mt-2 animate-up">
            <div className="mb-2">
              <Eyebrow className="mb-1.5">Giá trị tối thiểu · ${minAmt.toLocaleString("en-US")}</Eyebrow>
              <input
                type="range"
                min={0}
                max={200000}
                step={5000}
                value={minAmt}
                onChange={(e) => onMinAmt(Number(e.target.value))}
                aria-label="Giá trị giao dịch tối thiểu"
                className="w-full accent-primary"
              />
            </div>

            {LAYER_ORDER.filter((l) => KINDS_BY_LAYER[l].length > 0).map((layer) => (
              <div key={layer} className="mb-1.5">
                <div className="px-2 py-1 text-3xs uppercase tracking-[0.08em] text-ink-dim">
                  {LAYER_LABEL[layer]}
                </div>
                {KINDS_BY_LAYER[layer].map(([kind, label]) => (
                  <Check
                    key={kind}
                    checked={!mutedKinds[kind]}
                    label={label}
                    onChange={(v) => onKind(kind, !v)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
