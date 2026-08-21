import { useEffect, useMemo, useState } from "react";

import { api } from "../../../api/client";
import { useApi } from "../../../api/useApi";
import { useConsole } from "../../../context/ConsoleContext";
import type { GraphModel } from "../types/graph.types";
import { buildModel } from "../utils/graphHierarchy";
import { splitGraphComponents } from "../utils/graphComponents";

/**
 * Tải đồ thị và dựng mô hình một lần duy nhất.
 *
 * `buildModel` chạy suy luận chặng/tier/cụm cho toàn bộ đồ thị, không rẻ. Nó
 * chỉ phụ thuộc dữ liệu API nên phải nằm ngoài mọi thay đổi bộ lọc — nếu để
 * trong cùng memo với filter thì mỗi lần kéo thanh trượt lại tính lại từ đầu.
 */
export function useGraphModel(limit = 600) {
  // Đồ thị mạng lưới bám theo bộ dữ liệu toàn cục ở header: đổi bộ thì cả đồ
  // thị gieo lại từ cảnh báo của đúng bộ đó.
  const { dataset } = useConsole();
  const state = useApi(() => api.entityGraph(limit, dataset), [limit, dataset]);
  const [activeComponentId, setActiveComponentId] = useState<string | null>(null);

  const components = useMemo(() => (state.data ? splitGraphComponents(state.data) : []), [state.data]);
  const selected = components.find((component) => component.id === activeComponentId) ?? components[0] ?? null;

  useEffect(() => {
    if (selected && selected.id !== activeComponentId) setActiveComponentId(selected.id);
  }, [selected, activeComponentId]);

  const model: GraphModel | null = useMemo(() => {
    if (!selected?.graph.nodes.length) return null;
    return buildModel(selected.graph);
  }, [selected]);

  return {
    model,
    components,
    activeComponentId: selected?.id ?? null,
    setActiveComponentId,
    loading: state.loading,
    error: state.error,
    reload: state.reload,
  };
}
