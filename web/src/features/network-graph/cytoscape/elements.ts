import type { ElementDefinition } from "cytoscape";

import { usd } from "../../../api/fcFormat";
import type { RenderEdge, RenderGraph, RenderNode } from "../types/graph.types";

/**
 * Chuyển mô hình đồ thị sang phần tử Cytoscape.
 *
 * File này không import Cytoscape để làm gì ngoài kiểu dữ liệu, và không biết
 * gì về màu sắc — mọi quyết định thị giác nằm ở stylesheet.ts. Ở đây chỉ có ba
 * việc: xác định *cái gì là compound node*, *nhãn ngắn của mỗi đỉnh là gì*, và
 * *cạnh mang theo con số nào khi được chọn*.
 */

/** Mức rủi ro dùng chung cho đỉnh và cạnh. Cùng ngưỡng với riskColor(). */
export function riskClass(risk: number): "" | "risk-warn" | "risk-crit" {
  if (risk >= 80) return "risk-crit";
  if (risk >= 60) return "risk-warn";
  return "";
}

/**
 * Nhãn cạnh — chỉ dựng khi cạnh được chọn, nhưng tính sẵn ở đây cho rẻ.
 *
 * Ưu tiên số giao dịch thật. Nếu quan hệ không có giao dịch nào đứng sau (sở
 * hữu, thiết bị dùng chung, chuyển on-chain) thì nói đúng loại quan hệ chứ
 * không hiển thị "0 giao dịch" — con số 0 dễ bị đọc thành "đã kiểm tra và
 * không có", trong khi sự thật là "loại quan hệ này vốn không sinh giao dịch".
 */
export function edgeLabel(e: RenderEdge): string {
  const parts: string[] = [];
  const currencies = Object.entries(e.amountsByCurrency);
  if (currencies.length === 1) {
    parts.push(currencies[0][1] >= 1000 ? usd(currencies[0][1]) : `${currencies[0][1]} ${currencies[0][0]}`);
  } else if (currencies.length > 1) {
    // Không cộng nhiều loại tiền thành một số (§8).
    parts.push(`${currencies.length} loại tiền`);
  } else if (e.amt != null) {
    parts.push(usd(e.amt));
  }
  if (e.txCount > 0) parts.push(`${e.txCount} giao dịch`);
  else if (e.count > 1) parts.push(`${e.count} quan hệ`);
  return parts.join(" · ");
}

/**
 * Nhãn ngắn của đỉnh.
 *
 * Cụm thu gọn mang dạng "Tài khoản gom +4" — đọc một cái là biết đây là nhiều
 * thực thể cùng loại chứ không phải một thực thể tên lạ.
 */
function shortLabel(n: RenderNode): string {
  if (n.kind === "cluster") return `${n.label} +${n.count}`;
  return n.shortLabel || n.label;
}

/**
 * Chỗ đứt của mạch điều tra, đã quy về đỉnh đang hiển thị.
 *
 * KHÔNG phải quan hệ. Nó là ghi chú điều tra: hai chặng liền nhau mà dữ liệu
 * hiện có không quan sát được liên kết nào giữa chúng. Dựng thành phần tử
 * riêng với class riêng, không bao giờ trộn vào `graph.edges` — nhập chung thì
 * một khoảng trống bằng chứng sẽ bị đếm như một quan hệ có thật.
 */
export interface GapLink {
  id: string;
  fromId: string;
  toId: string;
}

interface BuildOptions {
  /** Cụm đang mở → dựng compound parent bao các thành viên. */
  openClusterIds: Set<string>;
  /** Nhãn hiển thị của cụm, tra theo id. */
  clusterLabels: Map<string, string>;
  gaps: GapLink[];
}

export function buildElements(graph: RenderGraph, opts: BuildOptions): ElementDefinition[] {
  const out: ElementDefinition[] = [];

  // Compound parent cho cụm đang mở. Cytoscape yêu cầu parent phải tồn tại
  // trước khi con tham chiếu tới nó, nên dựng trước toàn bộ đỉnh thường.
  const parents = new Set<string>();
  for (const n of graph.nodes) {
    if (n.parentClusterId && opts.openClusterIds.has(n.parentClusterId)) {
      parents.add(n.parentClusterId);
    }
  }
  for (const id of parents) {
    const label = opts.clusterLabels.get(id) ?? id;
    out.push({
      group: "nodes",
      data: { id: `CL:${id}`, clusterLabel: label, tier: 3 },
      classes: "cluster-parent",
      selectable: false,
      grabbable: false,
    });
  }

  for (const n of graph.nodes) {
    const classes: string[] = [];
    if (n.kind === "cluster") classes.push("collapsed-cluster");
    if (n.negative) classes.push("negative");
    const rc = riskClass(n.risk);
    if (rc) classes.push(rc);

    const parent =
      n.parentClusterId && opts.openClusterIds.has(n.parentClusterId) ? `CL:${n.parentClusterId}` : undefined;

    out.push({
      group: "nodes",
      data: {
        id: n.id,
        label: n.label,
        short: shortLabel(n),
        clusterLabel: shortLabel(n),
        etype: n.type,
        tier: n.tier,
        risk: n.risk,
        role: n.role,
        sub: n.sub,
        count: n.count,
        isCluster: n.kind === "cluster",
        parent,
      },
      classes: classes.join(" "),
    });
  }

  const present = new Set(graph.nodes.map((n) => n.id));
  for (const e of graph.edges) {
    // Cạnh treo làm layout văng — bỏ trước khi đưa vào Cytoscape.
    if (!present.has(e.s) || !present.has(e.t)) continue;
    const classes: string[] = [];
    if (e.money) classes.push("money");
    if (e.inferred) classes.push("inferred");
    else classes.push("observed");
    if (e.layer === "device") classes.push("device-link");
    if (graph.byId[e.s]?.negative || graph.byId[e.t]?.negative) classes.push("verified-negative");

    out.push({
      group: "edges",
      data: {
        id: e.id,
        source: e.s,
        target: e.t,
        kind: e.kind,
        edgeLabel: edgeLabel(e),
        txCount: e.txCount,
        money: e.money,
        inferred: e.inferred,
        layer: e.layer,
      },
      classes: classes.join(" "),
    });
  }

  for (const gap of opts.gaps) {
    if (!present.has(gap.fromId) || !present.has(gap.toId)) continue;
    out.push({
      group: "edges",
      data: { id: `GAP:${gap.id}`, source: gap.fromId, target: gap.toId, isGap: true },
      classes: "evidence-gap",
    });
  }

  return out;
}
