import { durationMinutes, usd } from "../../../api/fcFormat";
import { C } from "../../../design/palette";
import type { GraphModel, MoneyPath } from "../types/graph.types";
import type { ReplayStatus } from "../stores/graph.store";

interface Props {
  paths: MoneyPath[];
  activeId: string | null;
  model: GraphModel;
  onPick: (id: string | null) => void;
  onStep: (delta: number) => void;
  /** Số chỗ đứt bằng chứng trong mạch điều tra hiện tại. */
  missingLinks: number;
  replayStatus: ReplayStatus;
  replayIndex: number;
  replaySpeed: 0.5 | 1 | 2;
  onReplay: () => void;
  onPause: () => void;
  onRestart: () => void;
  onSpeed: (speed: 0.5 | 1 | 2) => void;
}

/**
 * Bảng xếp hạng đường tiền.
 *
 * Mỗi dòng phải trả lời được "có đáng lần theo không" mà không cần bấm vào:
 * bao nhiêu chặng, bao nhiêu tiền, mất bao lâu, qua mấy kênh, tin được tới đâu.
 */

/** Nút thắt của đường, viết theo từng loại tiền. */
function pathAmount(path: { amountUsd: number; amountByCurrency: Record<string, number> }): string {
  const entries = Object.entries(path.amountByCurrency ?? {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length) {
    const [currency, value] = entries[0];
    const more = entries.length > 1 ? ` +${entries.length - 1}` : "";
    return `${value.toLocaleString("vi-VN", { maximumFractionDigits: 0 })} ${currency}${more}`;
  }
  return path.amountUsd > 0 ? usd(path.amountUsd) : "chưa có số tiền";
}

/** Một câu nói vì sao đường này đáng nhìn.
 *
 * Bảng cũ chỉ có "2 chặng · 1 kênh · 8.5 ngày · tin cậy 1.00" — toàn số đo, không
 * câu nào nói tại sao đáng ngờ. Chuyên viên phải tự suy ra, và với 12 đường thì
 * không ai suy hết. Câu này ghép các dấu hiệu thật sự đọc được từ dữ liệu.
 */
function pathStory(path: {
  hops: number;
  durationMin: number;
  riskAvg?: number;
  amountByCurrency: Record<string, number>;
}): string | null {
  const signals: string[] = [];
  const hours = path.durationMin / 60;
  if (path.hops >= 3) signals.push(`đi qua ${path.hops} chặng trung gian`);
  if (path.durationMin > 0 && hours <= 2) signals.push("tiền rời đi trong vòng 2 giờ");
  else if (path.durationMin > 0 && hours <= 24) signals.push("hoàn tất trong vòng một ngày");
  if ((path.riskAvg ?? 0) >= 80) signals.push("mọi tài khoản trên đường đều rủi ro cao");
  return signals.length ? signals.join(" · ") : null;
}

export function MoneyPathPanel({
  paths,
  activeId,
  model,
  onPick,
  onStep,
  missingLinks,
  replayStatus,
  replayIndex,
  replaySpeed,
  onReplay,
  onPause,
  onRestart,
  onSpeed,
}: Props) {
  if (!paths.length) {
    return (
      <p className="px-3 py-4 text-xs text-ink-low">
        Chưa tìm được đường tiền nào. Thử hạ ngưỡng giá trị tối thiểu, hoặc bật lại lớp Dòng tiền.
      </p>
    );
  }

  const idx = paths.findIndex((p) => p.id === activeId);

  const active = paths.find((p) => p.id === activeId) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Dòng tóm tắt đường đang chọn: khi trình bày, đây là câu duy nhất cần
          đọc to lên. Chuỗi chặng viết đầy đủ chứ không chỉ hai đầu. */}
      {active && (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-primary-line bg-primary-soft px-3 py-1.5">
          <span className="font-mono text-2xs text-ink-hi">Đường tiền ưu tiên #{paths.indexOf(active) + 1}</span>
          <span className="min-w-0 flex-1 truncate text-2xs text-ink-mid">
            {active.nodeIds.map((id) => model.byId[id]?.shortLabel ?? id).join(" → ")}
          </span>
          <span className="tabular font-mono text-2xs text-ink-hi">{pathAmount(active)}</span>
          <span className="font-mono text-3xs text-ink-low">{active.hops} chặng</span>
          <span className="font-mono text-3xs text-ink-low">
            {durationMinutes(active.durationMin)}
          </span>
          <span className="font-mono text-3xs text-ink-low">tin cậy {active.confidence.toFixed(2)}</span>
          {missingLinks > 0 && (
            <span className="rounded bg-warn/10 px-1.5 py-px font-mono text-3xs text-warn-soft">
              {missingLinks} thiếu liên kết
            </span>
          )}
          <div className="ml-auto flex items-center gap-1 border-l border-primary-line pl-2">
            <button
              type="button"
              onClick={replayStatus === "playing" ? onPause : onReplay}
              className="flex h-5 w-5 items-center justify-center rounded-full border border-primary-line bg-app text-[8px] text-primary hover:bg-elev"
              aria-label={replayStatus === "playing" ? "Tạm dừng phát luồng" : "Phát luồng tiền"}
            >
              {replayStatus === "playing" ? "❚❚" : "▶"}
            </button>
            <span className="w-14 font-mono text-3xs text-ink-low">
              {replayStatus === "idle" ? "Phát luồng" : `${Math.min(replayIndex + 1, active.edgeIds.length)} / ${active.edgeIds.length}`}
            </span>
            <button type="button" onClick={onRestart} className="px-1 text-3xs text-ink-low hover:text-ink-hi" title="Phát lại">
              ↺
            </button>
            <select
              value={replaySpeed}
              onChange={(event) => onSpeed(Number(event.target.value) as 0.5 | 1 | 2)}
              aria-label="Tốc độ phát luồng"
              className="rounded border border-line bg-app px-1 py-0.5 font-mono text-3xs text-ink-low"
            >
              <option value={0.5}>0.5×</option>
              <option value={1}>1×</option>
              <option value={2}>2×</option>
            </select>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <span className="text-2xs text-ink-low">{paths.length} đường</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => onStep(-1)}
            disabled={idx <= 0}
            className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev disabled:opacity-40"
          >
            ‹ Trước
          </button>
          <button
            type="button"
            onClick={() => onStep(1)}
            disabled={idx >= paths.length - 1}
            className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev disabled:opacity-40"
          >
            Sau ›
          </button>
          {activeId && (
            <button
              type="button"
              onClick={() => onPick(null)}
              className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev"
            >
              Bỏ chọn
            </button>
          )}
        </div>
      </div>

      <ol className="min-h-0 flex-1 overflow-y-auto">
        {paths.map((p, i) => {
          const on = p.id === activeId;
          const from = model.byId[p.nodeIds[0]];
          const to = model.byId[p.nodeIds[p.nodeIds.length - 1]];
          return (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onPick(on ? null : p.id)}
                className={[
                  "flex w-full items-center gap-3 border-b border-line-faint px-3 py-2 text-left transition-colors",
                  on ? "bg-primary-soft" : "hover:bg-elev",
                ].join(" ")}
              >
                <span className={`font-mono text-2xs ${on ? "text-primary" : "text-ink-dim"}`}>#{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs text-ink-mid">
                    {from?.shortLabel ?? "?"} <span className="text-ink-dim">→</span> {to?.shortLabel ?? "?"}
                  </span>
                  <span className="mt-0.5 block font-mono text-3xs text-ink-low">
                    {p.hops} chặng · {p.channels} kênh · {durationMinutes(p.durationMin)}
                  </span>
                  {pathStory(p) && (
                    <span className="mt-0.5 block text-3xs leading-snug text-warn-soft">{pathStory(p)}</span>
                  )}
                </span>
                <span className="tabular flex-none text-right">
                  <span className="block font-mono text-xs text-ink-hi">{pathAmount(p)}</span>
                  {/* Cột tin cậy chỉ có nghĩa khi đường chứa cạnh suy luận. Ở chế
                      độ vận hành mọi cạnh đều quan sát trực tiếp nên nó luôn bằng
                      1.00 — một cột hằng số không nói lên điều gì, chỉ chiếm chỗ. */}
                  {p.confidence < 1 && (
                    <span
                      className="block font-mono text-3xs"
                      style={{ color: p.confidence >= 0.8 ? C.ok : p.confidence >= 0.6 ? C.warn : C.risk }}
                    >
                      tin cậy {p.confidence.toFixed(2)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
