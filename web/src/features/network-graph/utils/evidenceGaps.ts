import type { EvidenceGap, GNode, GraphModel, Stage } from "../types/graph.types";
import { STAGE_INDEX, STAGE_LABEL, STAGES } from "../types/graph.types";

/**
 * Tìm chỗ đứt của mạch điều tra.
 *
 * Mạch tiền của vụ việc đi qua các chặng theo thứ tự. Ở đâu hai chặng liền nhau
 * *đều có thực thể* nhưng giữa chúng không tồn tại một quan hệ nào — kể cả quan
 * hệ suy luận — thì đó là chỗ điều tra viên chưa chứng minh được, chứ không
 * phải chỗ không có gì xảy ra.
 *
 * Cách xử lý duy nhất trung thực là nói thẳng ra điều đó. Nối một cạnh giả cho
 * hình đẹp sẽ biến một khoảng trống bằng chứng thành một khẳng định, và bất kỳ
 * kết luận nào dựa lên nó đều mất giá trị pháp lý.
 */

/** Mô tả những gì đã biết ở hai đầu, dựa trên số liệu thật của mô hình. */
function describeKnown(from: GNode, to: GNode): string {
  const parts: string[] = [];
  if (from.outUsd > 0) parts.push(`${from.label} có dòng ra ghi nhận được`);
  else parts.push(`${from.label} xuất hiện trong mạng lưới`);
  if (to.inUsd > 0) parts.push(`${to.label} có dòng vào ghi nhận được`);
  else parts.push(`${to.label} tồn tại nhưng chưa có giao dịch nào gắn với nó`);
  return parts.join("; ");
}

/** Nguồn dữ liệu có khả năng lấp khoảng trống, theo cặp chặng. */
function suggestSource(from: Stage, to: Stage): string {
  if (to === "gateway") return "Sao kê nạp tiền của sàn, hoặc yêu cầu cung cấp thông tin gửi tới VASP";
  if (from === "gateway") return "Nhật ký rút tiền của sàn kèm địa chỉ ví đích";
  if (to === "crypto" || from === "crypto") return "Phân cụm địa chỉ on-chain, hoặc dữ liệu nhãn ví từ nhà cung cấp";
  if (to === "destination") return "Truy vết on-chain nhiều chặng tới ví đích";
  return "Dữ liệu giao dịch của tổ chức trung gian ở chặng này";
}

/** Chặng có thực thể đang hiện, theo đúng thứ tự mạch tiền. */
function occupiedStages(model: GraphModel): Stage[] {
  const used = new Set(model.nodes.filter((n) => !n.negative).map((n) => n.stage));
  return STAGES.filter((s) => used.has(s));
}

/** Đại diện của một chặng: rủi ro cao nhất, bỏ qua đối chứng và băng phụ. */
function representative(model: GraphModel, stage: Stage): GNode | null {
  const candidates = model.nodes.filter((n) => n.stage === stage && !n.negative && n.band === "primary");
  if (!candidates.length) return null;
  return candidates.reduce((a, b) => (b.risk > a.risk ? b : a));
}

export function findEvidenceGaps(model: GraphModel): EvidenceGap[] {
  const stages = occupiedStages(model);
  if (stages.length < 2) return [];

  // Cặp chặng nào đã có ít nhất một quan hệ nối qua — bất kể loại nào.
  const linked = new Set<string>();
  model.edges.forEach((e) => {
    const a = model.byId[e.s];
    const b = model.byId[e.t];
    if (!a || !b || a.stage === b.stage) return;
    const lo = Math.min(STAGE_INDEX[a.stage], STAGE_INDEX[b.stage]);
    const hi = Math.max(STAGE_INDEX[a.stage], STAGE_INDEX[b.stage]);
    linked.add(`${lo}|${hi}`);
  });

  const gaps: EvidenceGap[] = [];
  for (let i = 0; i < stages.length - 1; i++) {
    const from = stages[i];
    const to = stages[i + 1];
    const key = `${STAGE_INDEX[from]}|${STAGE_INDEX[to]}`;
    if (linked.has(key)) continue;

    const a = representative(model, from);
    const b = representative(model, to);
    if (!a || !b) continue;

    gaps.push({
      id: `GAP-${from}-${to}`,
      fromStage: from,
      toStage: to,
      fromNodeId: a.id,
      toNodeId: b.id,
      known: describeKnown(a, b),
      missing: `Không có quan hệ nào trong dữ liệu nối ${STAGE_LABEL[from].toLowerCase()} với ${STAGE_LABEL[
        to
      ].toLowerCase()}`,
      suggestion: suggestSource(from, to),
    });
  }

  return gaps;
}

/**
 * Chỉ số sức khoẻ điều tra cho panel phải.
 *
 * "Độ phủ bằng chứng" đo phần quan hệ đứng vững được: quan sát trực tiếp tính
 * đủ, quan hệ suy luận chỉ tính theo độ tin cậy của chính nó, và mỗi chỗ đứt bị
 * trừ đi như một mắt xích thiếu hẳn. Con số này cố tình *không* làm đẹp — nó là
 * thứ phải nói ra khi bảo vệ hồ sơ.
 */
export interface InvestigationHealth {
  coveragePct: number;
  openQuestions: number;
  missingLinks: number;
  alternatives: number;
  weakInferences: number;
}

export function investigationHealth(model: GraphModel, gaps: EvidenceGap[]): InvestigationHealth {
  const observed = model.edges.filter((e) => !e.inferred).length;
  const inferred = model.edges.filter((e) => e.inferred);
  const inferredWeight = inferred.reduce((s, e) => s + (e.conf ?? 0.5), 0);
  const weak = inferred.filter((e) => (e.conf ?? 1) < 0.7).length;

  const total = model.edges.length + gaps.length;
  const covered = observed + inferredWeight;
  const coveragePct = total ? Math.round((covered / total) * 100) : 0;

  return {
    coveragePct,
    // Mỗi chỗ đứt và mỗi suy luận yếu đều là một câu hỏi chưa trả lời được.
    openQuestions: gaps.length + weak,
    missingLinks: gaps.length,
    alternatives: model.nodes.filter((n) => n.negative).length,
    weakInferences: weak,
  };
}
