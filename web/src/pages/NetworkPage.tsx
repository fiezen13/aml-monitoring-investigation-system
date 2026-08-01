import {
  Background,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Building2,
  Flag,
  Layers,
  ListFilter,
  RotateCcw,
  UserRound,
  Wallet,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ReasonModal } from "../components/common/ReasonModal";
import { useApp } from "../context/AppContext";
import { NETWORK_EDGES, NETWORK_NODES, getCase } from "../data/mockCases";
import type { NetworkNode } from "../types";

type FlowNodeData = { entity: NetworkNode };
type FlowNode = Node<FlowNodeData, "entity">;

const NODE_ICON = {
  subject: UserRound,
  mule: UserRound,
  company: Building2,
  wallet: Wallet,
  bank: Building2,
} as const;

/** Node thực thể — chủ thể chính viền teal, thực thể rủi ro cao viền đỏ. */
function EntityNode({ data }: NodeProps<FlowNode>) {
  const { entity } = data;
  const Icon = NODE_ICON[entity.kind];
  const isPrimary = entity.risk === "primary";
  return (
    <div className="flex flex-col items-center gap-1.5">
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <div
        className={`flex h-14 w-14 items-center justify-center rounded-full border-2 ${
          isPrimary
            ? "border-primary bg-primary/20 text-primary shadow-[0_0_18px_rgba(0,178,169,0.45)]"
            : "border-risk bg-risk/10 text-risk"
        }`}
      >
        <Icon size={22} aria-hidden />
      </div>
      <div className="text-center">
        <div className="max-w-[130px] text-2xs font-semibold leading-tight text-ink-hi">
          {entity.label}
        </div>
        <div className="text-[9px] uppercase tracking-wide text-ink-low">
          {entity.sublabel}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}

const nodeTypes = { entity: EntityNode };

const POSITIONS: Record<string, { x: number; y: number }> = {
  "n-company": { x: 320, y: 20 },
  "n-mule": { x: 120, y: 190 },
  "n-subject": { x: 540, y: 190 },
  "n-wallet": { x: 320, y: 360 },
};

function NetworkCanvas({ onSelect }: { onSelect: (id: string) => void }) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  const nodes: FlowNode[] = useMemo(
    () =>
      NETWORK_NODES.map((entity) => ({
        id: entity.id,
        type: "entity" as const,
        position: POSITIONS[entity.id] ?? { x: 0, y: 0 },
        data: { entity },
      })),
    [],
  );

  const edges: Edge[] = useMemo(
    () =>
      NETWORK_EDGES.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        animated: true,
        style: {
          stroke: "#EF4444",
          strokeWidth: 1.5,
          strokeDasharray: "6 4",
        },
        labelStyle: { fill: "#F1F5F9", fontSize: 10, fontWeight: 700 },
        labelBgStyle: {
          fill: "#EF4444",
          fillOpacity: 0.85,
        },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 3,
      })),
    [],
  );

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        proOptions={{ hideAttribution: true }}
        style={{ background: "transparent" }}
        nodesDraggable
        nodesConnectable={false}
      >
        <Background color="rgba(148,163,184,0.12)" gap={26} />
        <MiniMap
          pannable
          className="!bottom-3 !right-3 !h-24 !w-36 rounded-panel border border-line !bg-side"
          nodeColor={(n) =>
            (n.data as FlowNodeData).entity.risk === "primary" ? "#00B2A9" : "#EF4444"
          }
          maskColor="rgba(7,20,34,0.7)"
        />
      </ReactFlow>

      {/* Chú giải */}
      <div className="absolute bottom-4 left-4 rounded-panel border border-line bg-panel/95 p-3">
        <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
          Chú giải
        </div>
        <ul className="space-y-1.5 text-2xs text-ink-mid">
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-primary" aria-hidden />
            Thực thể chính
          </li>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-risk" aria-hidden />
            Rủi ro cao (Structuring)
          </li>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-ink-low" aria-hidden />
            Đối tác / Ngân hàng
          </li>
          <li className="flex items-center gap-2">
            <span className="inline-block w-4 border-t-2 border-dashed border-risk" aria-hidden />
            Dòng tiền nghi vấn
          </li>
        </ul>
      </div>

      {/* Thanh công cụ */}
      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-panel border border-line bg-panel/95 p-1">
        <button type="button" aria-label="Phóng to" onClick={() => zoomIn()} className="rounded p-2 text-ink-mid hover:bg-elev hover:text-ink-hi">
          <ZoomIn size={14} />
        </button>
        <button type="button" aria-label="Thu nhỏ" onClick={() => zoomOut()} className="rounded p-2 text-ink-mid hover:bg-elev hover:text-ink-hi">
          <ZoomOut size={14} />
        </button>
        <button type="button" aria-label="Căn giữa" onClick={() => fitView()} className="rounded p-2 text-ink-mid hover:bg-elev hover:text-ink-hi">
          <RotateCcw size={14} />
        </button>
        <span className="mx-0.5 h-5 w-px bg-line" aria-hidden />
        <button type="button" className="inline-flex items-center gap-1 rounded p-2 text-2xs text-ink-mid hover:bg-elev hover:text-ink-hi">
          <ListFilter size={13} aria-hidden />
          Lọc
        </button>
        <button type="button" className="inline-flex items-center gap-1 rounded p-2 text-2xs text-ink-mid hover:bg-elev hover:text-ink-hi">
          <Layers size={13} aria-hidden />
          Lớp hiển thị
        </button>
      </div>
    </div>
  );
}

/** Phân tích Mạng lưới Giao dịch — GRAPH-008, panel chi tiết thực thể bên phải. */
export function NetworkPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const amlCase = getCase(caseId ?? "") ?? getCase("CASE-2026-014");
  const [selectedId, setSelectedId] = useState<string>("n-subject");
  const [panelOpen, setPanelOpen] = useState(true);
  const [sarModal, setSarModal] = useState(false);

  const selected = NETWORK_NODES.find((n) => n.id === selectedId) ?? NETWORK_NODES[0];
  const related = NETWORK_NODES.filter((n) => n.id !== selected.id).slice(0, 2);

  return (
    <div className="relative -m-4 flex h-[calc(100vh-56px)]">
      <div className="min-w-0 flex-1">
        <ReactFlowProvider>
          <NetworkCanvas
            onSelect={(id) => {
              setSelectedId(id);
              setPanelOpen(true);
            }}
          />
        </ReactFlowProvider>
      </div>

      {/* Panel chi tiết bên phải */}
      {panelOpen && (
        <aside className="flex w-[320px] shrink-0 flex-col overflow-y-auto border-l border-line bg-panel">
          <div className="flex items-start justify-between p-4 pb-0">
            <span className="rounded-control bg-risk px-2 py-0.5 text-2xs font-bold uppercase tracking-wider text-white">
              Cảnh báo: Structuring
            </span>
            <button
              type="button"
              aria-label="Đóng panel"
              onClick={() => setPanelOpen(false)}
              className="rounded p-1 text-ink-mid hover:bg-elev hover:text-ink-hi"
            >
              <X size={15} />
            </button>
          </div>
          <div className="space-y-4 p-4">
            <h2 className="text-[17px] font-bold text-ink-hi">{selected.label}</h2>

            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-control border border-line bg-elev p-2.5">
                <div className="text-2xs uppercase tracking-wide text-ink-low">Điểm rủi ro</div>
                <div className="tabular mt-0.5 text-[18px] font-bold text-risk">
                  {amlCase?.risk_score ?? 92}/100
                </div>
              </div>
              <div className="rounded-control border border-line bg-elev p-2.5">
                <div className="text-2xs uppercase tracking-wide text-ink-low">Tổng GD (30D)</div>
                <div className="tabular mt-0.5 text-[18px] font-bold text-ink-hi">1.85B</div>
              </div>
            </div>

            <div className="rounded-panel border border-primary/25 bg-primary-soft p-3">
              <div className="flex items-center gap-1.5 text-[13px] font-semibold text-primary">
                ✦ Phân tích AI Copilot
              </div>
              <p className="mt-1.5 text-2xs leading-relaxed text-ink-mid">
                Phát hiện chu trình quay vòng vốn (Circular flow) giữa 4 thực thể. Các khoản
                tiền được chia nhỏ dưới ngưỡng 500 triệu VND (ngưỡng báo cáo) và luân chuyển
                nhanh chóng trong vòng 24 giờ.
              </p>
              <ul className="mt-2 space-y-1 text-2xs text-ink-mid">
                <li className="flex items-center gap-1.5">
                  <span className="text-ok">✓</span> Trùng khớp hành vi Structuring loại A
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-ok">✓</span> Tài khoản Mule được tạo mới &lt; 30 ngày
                </li>
              </ul>
              <p className="mt-2 text-2xs text-ink-low">
                Nguồn: Network Analysis Tool · GRAPH-008
              </p>
            </div>

            <div>
              <div className="mb-2 text-[13px] font-semibold text-ink-hi">
                Mối quan hệ liên quan
              </div>
              <div className="space-y-1.5">
                {related.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setSelectedId(r.id)}
                    className="flex w-full items-center justify-between rounded-control border border-line bg-elev px-3 py-2 text-left hover:border-primary/40"
                  >
                    <div>
                      <div className="text-[13px] font-medium text-ink-hi">{r.label}</div>
                      <div className="text-2xs text-ink-low">{r.sublabel}</div>
                    </div>
                    <span className="text-ink-low">›</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[13px] font-semibold text-ink-hi">
                  Lịch sử Giao dịch Gần đây
                </span>
                <button type="button" className="text-2xs font-medium text-primary hover:underline">
                  XEM TẤT CẢ
                </button>
              </div>
              <div className="rounded-control border border-line bg-elev px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-2xs text-ink-mid">
                    <span className="h-1.5 w-1.5 rounded-full bg-risk" aria-hidden />
                    Hôm nay, 14:20
                  </span>
                  <span className="tabular text-2xs font-bold text-risk">+ 450,000,000 VND</span>
                </div>
                <div className="mt-0.5 text-2xs text-ink-low">Chuyển từ Blue Ocean Co.</div>
              </div>
            </div>
          </div>

          <div className="mt-auto space-y-2 border-t border-line p-4">
            <button
              type="button"
              onClick={() => setSarModal(true)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-control bg-primary py-2.5 text-[14px] font-semibold text-app hover:bg-primary-hover"
            >
              <Flag size={14} aria-hidden />
              Gửi Báo cáo SAR Ngay
            </button>
            <button
              type="button"
              onClick={() => navigate(`/cases/${amlCase?.case_id ?? "CASE-2026-014"}`)}
              className="w-full py-1.5 text-[13px] font-medium text-ink-mid hover:text-ink-hi"
            >
              Mở rộng điều tra vụ việc
            </button>
          </div>
        </aside>
      )}

      <ReasonModal
        open={sarModal}
        title="Chuyển sang soạn bản nháp SAR"
        description="Không có đường tắt từ mạng lưới tới xuất hồ sơ — bản nháp SAR phải qua kiểm chứng và người phê duyệt (Hình 4). Nhập lý do để tiếp tục."
        confirmLabel="Mở bản nháp SAR-2026-007"
        onClose={() => setSarModal(false)}
        onConfirm={() => {
          setSarModal(false);
          pushToast({
            tone: "success",
            title: "Đã mở bản nháp SAR-2026-007",
            detail: "Hành động được ghi vào audit trail.",
          });
          navigate("/sar/SAR-2026-007/edit");
        }}
      />
    </div>
  );
}
