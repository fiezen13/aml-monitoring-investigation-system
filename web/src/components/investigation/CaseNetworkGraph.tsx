import { ReactFlowProvider } from "@xyflow/react";
import { Maximize2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { useApi } from "../../api/useApi";
import { NetworkCanvas } from "../../pages/NetworkPage";
import { Panel } from "../common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../common/States";

/**
 * Đồ thị mạng lưới của MỘT vụ việc, nhúng thẳng vào trang vụ việc.
 *
 * Mục đích của đồ thị là để chuyên viên quan sát dòng tiền quanh chủ thể ngay
 * khi đang đọc vụ — không phải nhảy sang một trang riêng rồi quên mất đang xem
 * vụ nào. Mỗi vụ có một đồ thị riêng (dựng từ giao dịch thật của chủ thể), nên
 * nó sống ngay tại đây. Nút mở rộng đưa sang view toàn màn hình `/network/:id`
 * khi cần thao tác kỹ.
 */
export function CaseNetworkGraph({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const graph = useApi(() => api.network(caseId), [caseId]);

  return (
    <Panel
      title="Đồ thị mạng lưới của vụ"
      action={
        graph.data ? (
          <button
            type="button"
            onClick={() => navigate(`/network/${caseId}`)}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
          >
            <Maximize2 size={12} aria-hidden />
            Mở toàn màn hình
          </button>
        ) : undefined
      }
    >
      {graph.loading ? (
        <LoadingSkeleton rows={5} />
      ) : graph.error ? (
        <ErrorState detail={graph.error} onRetry={graph.reload} />
      ) : !graph.data || graph.data.nodes.length === 0 ? (
        <EmptyState
          title="Chưa dựng được đồ thị"
          detail="Vụ việc này chưa có đủ giao dịch giữa các tài khoản để dựng mạng lưới."
        />
      ) : (
        <div className="space-y-2">
          <p className="text-2xs text-ink-low">
            Dựng từ {graph.data.transactions.length} giao dịch thật giữa {graph.data.nodes.length} tài khoản quanh chủ
            thể {graph.data.subject_account_key}. Cạnh nét đứt đỏ = dòng tiền vượt ngưỡng heuristic (chưa phải kết luận).
          </p>
          {/* Khung cao cố định để đồ thị không đẩy phần dưới của trang đi mất;
              vẫn kéo/thả/zoom được, hoặc mở toàn màn hình khi cần rộng hơn. */}
          <div className="h-[440px] overflow-hidden rounded-panel border border-line bg-app">
            <ReactFlowProvider>
              <NetworkCanvas
                entities={graph.data.nodes}
                relationships={graph.data.edges}
                onSelect={() => {}}
              />
            </ReactFlowProvider>
          </div>
        </div>
      )}
    </Panel>
  );
}
