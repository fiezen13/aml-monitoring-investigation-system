import { useMemo } from "react";

import type { GraphModel, MoneyPath } from "../types/graph.types";
import type { Lead } from "../utils/pathRanking";
import { buildLeads, detectCycles, findMoneyPaths } from "../utils/pathRanking";

/**
 * Đường tiền, gợi ý điều tra và chu trình.
 *
 * Ba thứ này đều duyệt toàn đồ thị nên tính chung một chỗ và chỉ tính lại khi
 * mô hình hoặc cặp nguồn/đích đổi.
 */
export function useMoneyPaths(
  model: GraphModel | null,
  source: string | null,
  target: string | null,
): { paths: MoneyPath[]; leads: Lead[]; cycles: string[][] } {
  return useMemo(() => {
    if (!model) return { paths: [], leads: [], cycles: [] };
    const paths = findMoneyPaths(model, source, target);
    return {
      paths,
      leads: buildLeads(model, paths),
      cycles: detectCycles(model),
    };
  }, [model, source, target]);
}
