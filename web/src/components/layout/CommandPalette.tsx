import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { NAV } from "../../config/nav";
import { useConsole } from "../../context/ConsoleContext";

interface Entry {
  id: string;
  label: string;
  hint: string;
  group: string;
  go: () => void;
}

interface Props {
  /** Kết quả tra cứu thực thể từ API — alert, case, ví, tài khoản. */
  entities?: { id: string; label: string; kind: string; href: string }[];
  onQueryChange?: (q: string) => void;
}

/**
 * Bảng lệnh ⌘K. Hai nguồn kết quả: điều hướng tĩnh (luôn có, khớp cục bộ) và
 * tra cứu thực thể từ API (chỉ khi gõ ≥ 2 ký tự).
 *
 * Điều hướng để trước kết quả tra cứu — người dùng gõ ⌘K rồi "alert" hầu như
 * luôn muốn mở màn hình Alert Center chứ không phải một alert cụ thể nào đó.
 */
export function CommandPalette({ entities = [], onQueryChange }: Props) {
  const { paletteOpen, setPaletteOpen } = useConsole();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (paletteOpen) {
      setQ("");
      setCursor(0);
      // Chờ một khung hình cho phần tử vào DOM rồi mới lấy được con trỏ.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [paletteOpen]);

  useEffect(() => {
    onQueryChange?.(q);
  }, [q, onQueryChange]);

  const entries = useMemo<Entry[]>(() => {
    const needle = q.trim().toLowerCase();
    const nav: Entry[] = NAV.filter((it) => !needle || it.label.toLowerCase().includes(needle)).map((it) => ({
      id: `nav:${it.to}`,
      label: it.label,
      hint: it.section ?? "Điều hướng",
      group: "Màn hình",
      go: () => navigate(it.to),
    }));
    const kindLabel: Record<string, string> = {
      alert: "Cảnh báo",
      case: "Vụ việc",
      account: "Tài khoản",
      customer: "Khách hàng",
      entity: "Thực thể",
      wallet: "Ví",
      transaction: "Giao dịch",
    };
    const ents: Entry[] = entities.map((e) => ({
      id: `ent:${e.id}`,
      label: e.label,
      hint: kindLabel[e.kind.toLowerCase()] ?? e.kind,
      group: "Thực thể",
      go: () => navigate(e.href),
    }));
    return [...nav, ...ents];
  }, [q, entities, navigate]);

  useEffect(() => {
    if (cursor >= entries.length) setCursor(0);
  }, [entries.length, cursor]);

  if (!paletteOpen) return null;

  const run = (entry: Entry | undefined) => {
    if (!entry) return;
    entry.go();
    setPaletteOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-modal flex items-start justify-center bg-scrim pt-[12vh] backdrop-blur-[2px]"
      onClick={() => setPaletteOpen(false)}
      role="presentation"
    >
      <div
        className="w-[min(620px,92vw)] overflow-hidden rounded-panel border border-line-strong bg-raised shadow-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Bảng lệnh"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-3.5 py-3">
          <Search size={15} className="flex-none text-ink-low" aria-hidden />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((c) => (c + 1) % Math.max(1, entries.length));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((c) => (c - 1 + entries.length) % Math.max(1, entries.length));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(entries[cursor]);
              } else if (e.key === "Escape") {
                setPaletteOpen(false);
              }
            }}
            placeholder="Tìm màn hình, thực thể, vụ việc, cảnh báo…"
            aria-label="Tìm kiếm"
            className="flex-1 bg-transparent text-lg text-ink-hi outline-none placeholder:text-ink-dim"
          />
          <kbd className="flex-none rounded-[5px] border border-line-strong px-1.5 py-0.5 font-mono text-2xs text-ink-low">
            ESC
          </kbd>
        </div>

        <div className="max-h-[46vh] overflow-y-auto py-1.5">
          {entries.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-ink-low">Không có kết quả cho “{q}”</div>
          )}
          {entries.map((e, i) => {
            const prev = entries[i - 1];
            return (
              <div key={e.id}>
                {e.group !== prev?.group && <div className="fc-eyebrow px-4 pb-1 pt-2.5">{e.group}</div>}
                <button
                  type="button"
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => run(e)}
                  className={`flex w-full items-center gap-2.5 px-4 py-2 text-left transition-colors ${
                    i === cursor ? "bg-elev text-ink-hi" : "text-ink-mid"
                  }`}
                >
                  <span className="truncate-1 flex-1 text-base">{e.label}</span>
                  <span className="flex-none text-2xs text-ink-low">{e.hint}</span>
                  {i === cursor && <CornerDownLeft size={12} className="flex-none text-primary" aria-hidden />}
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-3 border-t border-line px-4 py-2 text-2xs text-ink-dim">
          <span>↑↓ chọn</span>
          <span>⏎ mở</span>
          <span>Esc để đóng</span>
        </div>
      </div>
    </div>
  );
}
