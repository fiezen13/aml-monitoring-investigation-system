import { Bell, Search } from "lucide-react";
import { useState } from "react";

import { useApp } from "../../context/AppContext";
import { useConsole, WINDOW_LABEL, type TimeWindow } from "../../context/ConsoleContext";
import { PulseDot } from "../fc/primitives";

interface Props {
  /** Đường dẫn hiển thị của màn hình hiện tại. */
  crumb?: string;
  /** Số cảnh báo mức critical, hiện ở chuông thông báo. */
  criticalCount?: number;
}

const WORLDS = ["FIN-07 Primary", "FIN-07 Stress Sim"];
const WINDOWS: TimeWindow[] = ["1h", "24h", "7d", "30d"];

export function Header({ crumb, criticalCount = 0 }: Props) {
  const { currentUser } = useApp();
  const { window: win, setWindow, world, setWorld, setPaletteOpen } = useConsole();
  const [bellOpen, setBellOpen] = useState(false);

  const initials = (currentUser?.name ?? "")
    .split(" ")
    .slice(-2)
    .map((w) => w[0])
    .join("");

  return (
    <header className="flex h-[52px] flex-none items-center gap-3 border-b border-line bg-side px-4">
      <div className="truncate-1 flex-none text-xl font-semibold">{crumb}</div>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="flex min-w-[110px] flex-[0_1_270px] items-center gap-2 overflow-hidden rounded-control border border-line bg-sunken px-2.5 py-[5px] text-ink-low transition-colors hover:border-primary/40"
      >
        <Search size={13} className="flex-none" aria-hidden />
        <span className="truncate-1 flex-1 text-left text-base">Tìm entity, case, alert…</span>
        <span className="flex-none rounded-[5px] border border-line-strong/80 px-1.5 font-mono text-2xs">⌘K</span>
      </button>

      <div className="flex-1" />

      <select
        aria-label="Thế giới mô phỏng"
        value={world}
        onChange={(e) => setWorld(e.target.value)}
        className="fc-input py-[5px] text-base"
      >
        {WORLDS.map((w) => (
          <option key={w} value={w}>
            World: {w}
          </option>
        ))}
      </select>

      <select
        aria-label="Cửa sổ thời gian"
        value={win}
        onChange={(e) => setWindow(e.target.value as TimeWindow)}
        className="fc-input py-[5px] text-base"
      >
        {WINDOWS.map((w) => (
          <option key={w} value={w}>
            {WINDOW_LABEL[w]}
          </option>
        ))}
      </select>

      {/* Nhãn này không phải trang trí: toàn bộ dữ liệu trong console là tổng
          hợp, và người xem phải biết điều đó ở mọi màn hình. */}
      <span className="whitespace-nowrap rounded-[6px] border border-warn/40 bg-warn/10 px-2 py-[3px] font-mono text-2xs tracking-[0.08em] text-warn">
        SYNTHETIC
      </span>

      <div
        title="Trạng thái luồng dữ liệu"
        className="flex items-center gap-1.5 whitespace-nowrap text-xs text-ink-soft"
      >
        <PulseDot />
        LIVE
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setBellOpen((v) => !v)}
          aria-label="Thông báo"
          aria-expanded={bellOpen}
          className="relative p-1 text-ink-soft transition-colors hover:text-ink-hi"
        >
          <Bell size={17} strokeWidth={1.8} />
          {criticalCount > 0 && (
            <span className="absolute right-[3px] top-[2px] h-[7px] w-[7px] rounded-full border-[1.5px] border-side bg-risk" />
          )}
        </button>
        {bellOpen && (
          <div className="absolute right-0 top-full z-40 mt-1.5 w-72 rounded-panel border border-line bg-elev p-3 shadow-2xl">
            <div className="fc-eyebrow mb-2">Thông báo nội bộ</div>
            <p className="text-xs leading-relaxed text-ink-mid">
              {criticalCount} cảnh báo đang ở mức critical trong cửa sổ {WINDOW_LABEL[win]}. Thông báo chỉ phát trong
              nội bộ — hệ thống không có kênh nào gửi tới chủ thể đang bị rà soát.
            </p>
          </div>
        )}
      </div>

      <div
        title={`${currentUser?.name} · ${currentUser?.roleLabel}`}
        className="grid h-[30px] w-[30px] flex-none place-items-center rounded-full border border-primary/35 bg-gradient-to-br from-[#134B5F] to-[#0E2A44] text-xs font-semibold text-ok-soft"
      >
        {initials}
      </div>
    </header>
  );
}
