import { Plus, X } from "lucide-react";

import { evidenceTypeLabel } from "../../api/format";
import { useApp } from "../../context/AppContext";
import type { Evidence } from "../../types";
import { StatusBadge } from "../common/Badges";
import { EvidenceBody } from "../investigation/EvidenceBody";

interface EvidenceDrawerProps {
  evidenceId: string | null;
  evidence: Evidence[];
  onClose: () => void;
  onSelect: (id: string) => void;
}

/**
 * Ngăn bằng chứng — bảng bên phải hiển thị bằng chứng kỹ thuật số,
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
        aria-label="Ngăn bằng chứng"
      >
        <header className="flex items-start justify-between border-b border-line px-4 py-3">
          <div>
            <h2 className="text-h3 font-bold text-ink-hi">Chi tiết bằng chứng</h2>
            <p className="text-2xs text-ink-mid">
              {evidence.type ? evidenceTypeLabel(evidence.type) : evidence.title}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Đóng ngăn bằng chứng"
              onClick={onClose}
              className="rounded p-1 text-ink-mid hover:bg-elev hover:text-ink-hi"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <StatusBadge tone="primary" label="ĐANG XEM" />

          {/* Nội dung bằng chứng — render DỄ ĐỌC theo loại (EvidenceBody), không
              đổ JSON thô cho chuyên viên. */}
          <div className="rounded-panel border border-line bg-elev p-3 text-2xs text-ink-mid">
            {evidence.payload != null ? (
              <EvidenceBody type={evidence.type ?? ""} payload={evidence.payload} />
            ) : (
              <p className="leading-relaxed text-ink-mid">{evidence.description}</p>
            )}
          </div>
          <p className="text-2xs text-ink-low">
            Nguồn: <span className="text-info">{evidence.source}</span> — kết quả công cụ truy hồi, không phải số
            liệu do mô hình tự sinh.
          </p>

          <div>
            <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
              Bằng chứng khác trong vụ việc
            </div>
            <div className="space-y-1.5">
              {others.map((other) => (
                <button
                  key={other.id}
                  type="button"
                  onClick={() => onSelect(other.id)}
                  className="flex w-full items-center justify-between rounded-control border border-line bg-elev px-3 py-2 text-left hover:border-line-emphasis"
                >
                  <div className="min-w-0">
                    <div className="truncate text-body font-medium text-ink-hi">
                      {other.type ? evidenceTypeLabel(other.type) : other.title}
                    </div>
                    <div className="truncate text-2xs text-ink-low">Nguồn: {other.source}</div>
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
                title: "Bằng chứng chỉ được thêm qua hệ thống truy hồi",
                detail: "Giao diện không tự tạo dữ liệu chứng minh.",
              })
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-control bg-primary py-2 text-body font-semibold text-app hover:bg-primary-hover"
          >
            <Plus size={14} aria-hidden />
            Thêm bằng chứng mới
          </button>
        </footer>
      </aside>
    </div>
  );
}
