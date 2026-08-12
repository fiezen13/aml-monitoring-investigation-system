import { useMemo } from "react";

import { api } from "../../../api/client";
import { useApi } from "../../../api/useApi";
import type { GraphModel } from "../types/graph.types";
import { buildModel } from "../utils/graphHierarchy";

/**
 * Tải đồ thị và dựng mô hình một lần duy nhất.
 *
 * `buildModel` chạy suy luận chặng/tier/cụm cho toàn bộ đồ thị, không rẻ. Nó
 * chỉ phụ thuộc dữ liệu API nên phải nằm ngoài mọi thay đổi bộ lọc — nếu để
 * trong cùng memo với filter thì mỗi lần kéo thanh trượt lại tính lại từ đầu.
 */
export function useGraphModel(limit = 600) {
  const state = useApi(() => api.entityGraph(limit), [limit]);

  const model: GraphModel | null = useMemo(() => {
    if (!state.data?.nodes.length) return null;
    return buildModel(state.data);
  }, [state.data]);

  return { model, loading: state.loading, error: state.error, reload: state.reload };
}
