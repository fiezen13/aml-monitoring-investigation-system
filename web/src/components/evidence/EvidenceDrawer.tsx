import { ExternalLink, FileText, Plus, X, ZoomIn } from "lucide-react";

import { useApp } from "../../context/AppContext";
import type { Evidence } from "../../types";
import { StatusBadge } from "../common/Badges";

interface EvidenceDrawerProps {
  evidenceId: string | null;
  evidence: Evidence[];
  onClose: () => void;
  onSelect: (id: string) => void;
}

/**
 * Evidence Drawer — panel phải hiển thị bằng chứng kỹ thuật số,
 * bám bố cục screenshot "Hồ sơ Vụ việc CASE-2026-014".
 */
export function EvidenceDrawer({ evidenceId, evidence: allEvidence, onClose, onSelect }: EvidenceDrawerProps) {
  const { pushToast } = useApp();
  if (!evidenceId) return null;
  const evidence = allEvidence.find((item) => item.id === evidenceId);
  if (!evidence) return null;

  const others = allEvidence.filter((e) => e.id !== evidenceId).slice(0, 3);

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="flex h-full w-[380px] flex-col border-l border-line bg-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Evidence Drawer"
      >
        <header className="flex items-start justify-between border-b border-line px-4 py-3">
          <div>
            <h2 className="text-[15px] font-bold text-ink-hi">Evidence Drawer</h2>
            <p className="text-2xs text-ink-mid">Bằng chứng kỹ thuật số</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="tabular text-2xs text-ink-low">ID: {evidence.id}</span>
            <button
              type="button"
              aria-label="Đóng drawer"
              onClick={onClose}
              className="rounded p-1 text-ink-mid hover:bg-elev hover:text-ink-hi"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <StatusBadge tone="primary" label="ĐANG XEM" />

          {/* Vùng xem trước tài liệu */}
          <div className="relative overflow-hidden rounded-panel border border-line bg-elev">
            <div className="flex h-44 flex-col items-center justify-center gap-2 text-ink-low">
              <FileText size={34} aria-hidden />
              <span className="text-2xs uppercase tracking-wide">
                Xem trước {evidence.fileType}
              </span>
            </div>
            <div className="absolute bottom-2 left-2 flex gap-1.5">
              <button
                type="button"
                aria-label="Phóng to"
                onClick={() => pushToast({ tone: "info", title: "Bản ghi JSON đã được xác minh bằng hash" })}
                className="rounded-full bg-primary p-2 text-app hover:bg-primary-hover"
              >
                <ZoomIn size={13} />
              </button>
              <button
                type="button"
                aria-label="Mở trong cửa sổ mới"
                onClick={() => pushToast({ tone: "info", title: `Nguồn: ${evidence.source}` })}
                className="rounded-full border border-line bg-panel p-2 text-ink-mid hover:text-ink-hi"
              >
                <ExternalLink size={13} />
              </button>
            </div>
          </div>

          <div>
            <h3 className="text-[14px] font-bold text-ink-hi">{evidence.title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-mid">
              {evidence.description}
            </p>
            <p className="mt-2 text-2xs text-ink-low">
              Nguồn: <span className="text-info">{evidence.source}</span> — đây là kết
              quả công cụ, không phải số liệu do mô hình tự sinh (NT2).
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-control border border-line bg-elev p-2.5">
              <div className="text-2xs uppercase tracking-wide text-ink-low">Loại file</div>
              <div className="mt-1 flex items-center gap-1.5 text-2xs font-semibold text-ink-hi">
                <FileText size={12} className="text-risk" aria-hidden />
                {evidence.fileType}
              </div>
            </div>
            <div className="rounded-control border border-line bg-elev p-2.5">
              <div className="text-2xs uppercase tracking-wide text-ink-low">Kích thước</div>
              <div className="tabular mt-1 text-2xs font-semibold text-ink-hi">
                {evidence.fileSize}
              </div>
            </div>
          </div>

          <div>
            <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
              Bằng chứng khác trong case
            </div>
            <div className="space-y-1.5">
              {others.map((other) => (
                <button
                  key={other.id}
                  type="button"
                  onClick={() => onSelect(other.id)}
                  className="flex w-full items-center justify-between rounded-control border border-line bg-elev px-3 py-2 text-left hover:border-primary/40"
                >
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-medium text-ink-hi">
                      {other.title}
                    </div>
                    <div className="tabular text-2xs text-ink-low">
                      {other.id} · {other.fileSize}
                    </div>
                  </div>
                  <span className="text-ink-low">›</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <footer className="border-t border-line p-4">
          <button
            type="button"
            onClick={() =>
              pushToast({
                tone: "info",
                title: "Bằng chứng chỉ được thêm qua API truy hồi",
                detail: "Giao diện không tự tạo dữ liệu chứng minh.",
              })
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-control bg-primary py-2 text-[13px] font-semibold text-app hover:bg-primary-hover"
          >
            <Plus size={14} aria-hidden />
            Thêm bằng chứng mới
          </button>
        </footer>
      </aside>
    </div>
  );
}
