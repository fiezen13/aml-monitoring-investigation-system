import { C } from "../../../design/palette";
import type { EvidenceGap, RenderEdge, RenderGraph, RenderNode, ZoomLevel } from "../types/graph.types";
import { STAGE_LABEL } from "../types/graph.types";
import type { Emphasis } from "../utils/graphOpacity";
import type { ShapeKind } from "../utils/graphStyles";
import { EDGE_LEVEL, edgeColor, nodeRadius, pathStageColor, typeStyle } from "../utils/graphStyles";

/**
 * Engine vẽ đồ thị điều tra trên canvas.
 *
 * Không phải web component như bản cũ: engine giờ là một lớp thuần TypeScript
 * nhận canvas từ React. Đổi như vậy để state đi một chiều — React quyết định
 * *vẽ cái gì*, engine chỉ lo *vẽ thế nào* — và để không phải tạo lại instance
 * mỗi lần đổi bộ lọc, vốn là nguyên nhân giật của bản cũ.
 *
 * Toạ độ do layout ghi sẵn vào `RenderNode.x/y`; engine không tự chạy mô phỏng
 * lực nào cả.
 */

export interface EngineCallbacks {
  onSelectNode?: (id: string | null) => void;
  onSelectEdge?: (id: string | null) => void;
  onExpandNode?: (id: string) => void;
  onZoomLevel?: (level: ZoomLevel, zoom: number) => void;
  onHover?: (id: string | null) => void;
}

export interface EngineOptions {
  perf: boolean;
  showColumns: boolean;
  showMinimap: boolean;
  reducedMotion: boolean;
}

const ZOOM_MIN = 0.18;
const ZOOM_MAX = 4;

/**
 * Ngưỡng mức chi tiết nhãn.
 *
 * Hạ so với bản trước vì `fit()` của đồ thị 8 cột thường dừng quanh 0.65–0.8;
 * với ngưỡng cũ (0.62) màn hình mặc định rơi ngay vào chế độ "xa" và giấu gần
 * hết nhãn. Kích thước chữ giờ vẽ theo không gian màn hình nên nhãn vẫn đọc
 * được ở mức phóng thấp — ngưỡng chỉ còn quyết định *hiện bao nhiêu*, không
 * quyết định *to bao nhiêu*.
 */
const FAR_BELOW = 0.34;
const CLOSE_ABOVE = 1.15;

/** Đệm quanh đồ thị khi fit, tính bằng pixel màn hình chứ không phải world. */
const FIT_PADDING = 64;

/** Trần phóng khi fit — vượt quá thì đồ thị nhỏ trông bị "thổi" quá mức. */
const ZOOM_MAX_FIT = 1.8;

/** Chiều cao khối nhãn dưới mỗi đỉnh, world units, để fit không cắt mất chữ. */
const LABEL_BLOCK = 34;

/** Thời gian chuyển alpha khi focus đổi, ms. */
const FADE_MS = 190;

function zoomLevelOf(zoom: number): ZoomLevel {
  if (zoom < FAR_BELOW) return "far";
  if (zoom > CLOSE_ABOVE) return "close";
  return "medium";
}

/** Chỗ đứt đã quy về hai đỉnh đang hiển thị. */
export interface RenderGap {
  id: string;
  fromId: string;
  toId: string;
  gap: EvidenceGap;
}

/** Ô chữ đã chiếm chỗ, dùng cho lượt chống chồng nhãn. */
interface LabelBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface LabelPlan {
  primary: Set<string>;
  secondary: Set<string>;
}

interface Hull {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  label: string;
  /** Số đỉnh đang vẽ trong bao. */
  count: number;
  /** Tổng thành viên thật của cụm, kể cả phần đang gom trong đỉnh "+N". */
  total: number;
  risk: number;
  negative: boolean;
}

export class GraphEngine {
  private canvas: HTMLCanvasElement;
  private host: HTMLElement;
  private ctx: CanvasRenderingContext2D;
  private dpr = 1;
  private w = 0;
  private h = 0;

  private graph: RenderGraph = { nodes: [], edges: [], byId: {}, openClusters: [] };
  private emphasis: Emphasis | null = null;
  private opts: EngineOptions = { perf: false, showColumns: true, showMinimap: true, reducedMotion: false };
  private cb: EngineCallbacks = {};

  private zoom = 1;
  private panX = 0;
  private panY = 0;
  private level: ZoomLevel = "medium";

  private hoverId: string | null = null;
  private hoverEdgeId: string | null = null;
  private selectedNodeId: string | null = null;
  private selectedEdgeId: string | null = null;

  /** Alpha đang hiển thị, chạy dần về alpha mục tiêu của `emphasis`. */
  private alphaNow = new Map<string, number>();
  private fadeStart = 0;
  private raf = 0;
  private dirty = true;
  private ro: ResizeObserver | null = null;
  private tooltip: HTMLDivElement;
  private hulls: Hull[] = [];
  private gaps: RenderGap[] = [];
  private hoverGapId: string | null = null;
  private labelPlan: LabelPlan = { primary: new Set(), secondary: new Set() };
  private disposed = false;

  constructor(host: HTMLElement, canvas: HTMLCanvasElement, tooltip: HTMLDivElement) {
    this.host = host;
    this.canvas = canvas;
    this.tooltip = tooltip;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D không khả dụng");
    this.ctx = ctx;

    this.resize();
    this.ro = new ResizeObserver(() => {
      this.resize();
      this.invalidate();
    });
    this.ro.observe(host);
    this.bindEvents();
    this.loop();
  }

  dispose(): void {
    this.disposed = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    this.ro = null;
  }

  setCallbacks(cb: EngineCallbacks): void {
    this.cb = cb;
  }

  setOptions(opts: Partial<EngineOptions>): void {
    this.opts = { ...this.opts, ...opts };
    this.invalidate();
  }

  /** Thay đồ thị. Camera giữ nguyên trừ khi gọi `fit()` — không giật khi lọc. */
  setGraph(graph: RenderGraph): void {
    this.graph = graph;
    this.computeHulls();
    // Node mới xuất hiện bắt đầu từ alpha 0 để có hiệu ứng nở khi mở cụm.
    graph.nodes.forEach((n) => {
      if (!this.alphaNow.has(n.id)) this.alphaNow.set(n.id, this.opts.reducedMotion ? 1 : 0);
    });
    this.invalidate();
  }

  setGaps(gaps: RenderGap[]): void {
    this.gaps = gaps;
    this.invalidate();
  }

  setEmphasis(emphasis: Emphasis): void {
    this.emphasis = emphasis;
    this.fadeStart = performance.now();
    this.invalidate();
  }

  setSelection(nodeId: string | null, edgeId: string | null): void {
    this.selectedNodeId = nodeId;
    this.selectedEdgeId = edgeId;
    this.invalidate();
  }

  getZoom(): number {
    return this.zoom;
  }

  invalidate(): void {
    this.dirty = true;
  }

  // ===== camera =====

  /**
   * Phủ kín vùng vẽ.
   *
   * Hai chỗ bản trước làm sai: đệm cộng vào *toạ độ world* nên nó bị nhân lên
   * theo mức phóng — đồ thị càng nhỏ thì đệm càng chiếm tỷ lệ lớn; và trần
   * phóng 1.6 áp cho cả trường hợp đồ thị thưa. Giờ đệm tính bằng pixel màn
   * hình, và hộp bao lấy cả bán kính đỉnh lẫn khối nhãn bên dưới.
   */
  fit(): void {
    const vis = this.graph.nodes.filter((n) => !this.emphasis?.hidden.has(n.id));
    const use = vis.length ? vis : this.graph.nodes;
    if (!use.length || !this.w) return;

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    use.forEach((n) => {
      const r = this.radiusOf(n);
      minX = Math.min(minX, n.x - r);
      maxX = Math.max(maxX, n.x + r);
      minY = Math.min(minY, n.y - r);
      maxY = Math.max(maxY, n.y + r + LABEL_BLOCK);
    });
    // Chừa chỗ cho hàng nhãn chặng phía trên.
    minY -= 30;

    const bw = Math.max(1, maxX - minX);
    const bh = Math.max(1, maxY - minY);

    // Thanh thời gian nổi ở trên và chú giải nổi ở dưới nằm *đè* lên canvas,
    // nên vùng thực sự dùng được hẹp hơn chiều cao canvas. Không trừ ra thì ở
    // màn hình thấp, hàng nhãn chặng chui xuống dưới thanh thời gian.
    const topInset = 92;
    const bottomInset = 58;
    const availW = Math.max(80, this.w - FIT_PADDING * 2);
    const availH = Math.max(80, this.h - topInset - bottomInset);

    this.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX_FIT, Math.min(availW / bw, availH / bh)));
    this.panX = FIT_PADDING + (availW - bw * this.zoom) / 2 - minX * this.zoom;
    this.panY = topInset + (availH - bh * this.zoom) / 2 - minY * this.zoom;
    this.emitZoom();
    this.invalidate();
  }

  /** Tỷ lệ diện tích đồ thị chiếm trên vùng vẽ — dùng để kiểm tra bố cục. */
  coverage(): { widthPct: number; heightPct: number; zoom: number; tier1Px: number } {
    const use = this.graph.nodes.filter((n) => !this.emphasis?.hidden.has(n.id));
    if (!use.length || !this.w) return { widthPct: 0, heightPct: 0, zoom: this.zoom, tier1Px: 0 };
    const xs = use.map((n) => n.x);
    const ys = use.map((n) => n.y);
    const bw = (Math.max(...xs) - Math.min(...xs)) * this.zoom;
    const bh = (Math.max(...ys) - Math.min(...ys)) * this.zoom;
    const tier1 = use.find((n) => n.tier === 1);
    return {
      widthPct: Math.round((bw / this.w) * 100),
      heightPct: Math.round((bh / this.h) * 100),
      zoom: Number(this.zoom.toFixed(2)),
      tier1Px: tier1 ? Math.round(this.radiusOf(tier1) * 2 * this.zoom) : 0,
    };
  }

  /** Đưa một đỉnh vào giữa mà không đổi mức zoom — focus không được nhảy camera. */
  centerOn(id: string): void {
    const n = this.graph.byId[id];
    if (!n) return;
    this.panX = this.w / 2 - n.x * this.zoom;
    this.panY = this.h / 2 - n.y * this.zoom;
    this.invalidate();
  }

  zoomBy(factor: number): void {
    const nz = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, this.zoom * factor));
    const s = nz / this.zoom;
    this.panX = this.w / 2 - (this.w / 2 - this.panX) * s;
    this.panY = this.h / 2 - (this.h / 2 - this.panY) * s;
    this.zoom = nz;
    this.emitZoom();
    this.invalidate();
  }

  private emitZoom(): void {
    const lvl = zoomLevelOf(this.zoom);
    if (lvl !== this.level) {
      this.level = lvl;
      this.cb.onZoomLevel?.(lvl, this.zoom);
    }
  }

  private resize(): void {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = this.host.clientWidth;
    const h = this.host.clientHeight;
    if (!w || !h) return;
    this.dpr = dpr;
    this.w = w;
    this.h = h;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
  }

  // ===== hulls =====

  private computeHulls(): void {
    const groups = new Map<string, RenderNode[]>();
    this.graph.nodes.forEach((n) => {
      if (!n.parentClusterId) return;
      const arr = groups.get(n.parentClusterId);
      if (arr) arr.push(n);
      else groups.set(n.parentClusterId, [n]);
    });

    this.hulls = [];
    this.graph.openClusters.forEach((c) => {
      const members = groups.get(c.id);
      if (!members || members.length < 2) return;
      // Đệm phải tính từ mép đỉnh chứ không từ tâm, nếu không bao sẽ cắt vào
      // đỉnh to nhất trong cụm.
      const pad = 22;
      this.hulls.push({
        x0: Math.min(...members.map((m) => m.x - this.radiusOf(m))) - pad,
        x1: Math.max(...members.map((m) => m.x + this.radiusOf(m))) + pad,
        y0: Math.min(...members.map((m) => m.y - this.radiusOf(m))) - pad,
        y1: Math.max(...members.map((m) => m.y + this.radiusOf(m))) + pad + 26,
        label: c.label,
        count: members.length,
        total: c.memberIds.length,
        risk: c.risk,
        negative: c.negative,
      });
    });
  }

  // ===== loop =====

  private loop = (): void => {
    if (this.disposed) return;
    const fading = performance.now() - this.fadeStart < FADE_MS;
    if (this.dirty || fading || this.alphaSettling()) {
      this.dirty = false;
      this.draw();
    }
    this.raf = requestAnimationFrame(this.loop);
  };

  private alphaSettling(): boolean {
    if (!this.emphasis) return false;
    for (const n of this.graph.nodes) {
      const target = this.emphasis.nodeAlpha.get(n.id) ?? 1;
      const now = this.alphaNow.get(n.id) ?? target;
      if (Math.abs(now - target) > 0.01) return true;
    }
    return false;
  }

  private stepAlpha(id: string, target: number): number {
    if (this.opts.reducedMotion) {
      this.alphaNow.set(id, target);
      return target;
    }
    const now = this.alphaNow.get(id) ?? target;
    const next = now + (target - now) * 0.22;
    this.alphaNow.set(id, next);
    return next;
  }

  // ===== drawing =====

  private draw(): void {
    const g = this.ctx;
    if (!this.w || !this.h) return;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.clearRect(0, 0, this.w, this.h);

    g.save();
    g.translate(this.panX, this.panY);
    g.scale(this.zoom, this.zoom);

    if (this.opts.showColumns && !this.opts.perf) this.drawColumns(g);
    this.drawHulls(g);
    this.drawEdges(g);
    this.drawGaps(g);
    this.labelPlan = this.planLabels(g);
    this.drawNodes(g);

    g.restore();

    if (this.opts.showMinimap && !this.opts.perf) this.drawMinimap(g);
  }

  /**
   * Nhãn chặng, xếp thành một hàng thẳng phía trên đồ thị.
   *
   * Bản trước đặt nhãn theo đỉnh cao nhất của từng cột nên chúng nhấp nhô và
   * đọc như chú thích rời rạc. Căn về một đường ngang chung thì nó đọc như một
   * dải tiêu đề, và pipeline hiện ra trong một cái liếc.
   */
  /**
   * Quyết định nhãn nào được vẽ, theo thứ tự ưu tiên.
   *
   * Chạy trong *không gian màn hình* chứ không phải world, vì chữ có kích thước
   * cố định trên màn hình — hai đỉnh cách nhau đủ xa ở mức phóng này có thể
   * dính nhãn ở mức phóng khác. Tăng khoảng cách trong layout là cần nhưng
   * không đủ; phải có lượt kiểm tra thật sau khi biết mức phóng.
   *
   * Ưu tiên: đỉnh đang chọn → tier 1 và cụm → đỉnh trên đường tiền chính →
   * tier 2 → còn lại. Ai đến trước giữ chỗ; ai đến sau mà đè lên thì mất dòng
   * phụ trước, mất cả nhãn sau.
   */
  private planLabels(g: CanvasRenderingContext2D): LabelPlan {
    const plan: LabelPlan = { primary: new Set(), secondary: new Set() };
    const boxes: LabelBox[] = [];

    const priority = (n: RenderNode): number => {
      if (this.selectedNodeId === n.id) return 0;
      if (n.tier === 1 || n.kind === "cluster") return 1;
      if ((this.emphasis?.nodeAlpha.get(n.id) ?? 1) >= 0.99) return 2;
      if (n.tier === 2) return 3;
      return 4;
    };

    const overlaps = (a: LabelBox) =>
      boxes.some((b) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0);

    const sorted = [...this.graph.nodes]
      .filter((n) => !this.emphasis?.hidden.has(n.id))
      .filter((n) => (this.emphasis?.nodeAlpha.get(n.id) ?? 1) > 0.06)
      .sort((a, b) => priority(a) - priority(b));

    sorted.forEach((n) => {
      const forced = this.selectedNodeId === n.id || this.hoverId === n.id;
      if (this.level === "far" && n.tier !== 1 && n.kind !== "cluster" && !forced) return;

      const sx = n.x * this.zoom + this.panX;
      const sy = (n.y + this.radiusOf(n)) * this.zoom + this.panY;
      const size = n.tier === 1 ? 13 : n.tier === 2 ? 12 : 10.5;

      g.font = `${n.tier === 1 ? "600" : "500"} ${size}px Geist, sans-serif`;
      const text = this.level === "far" ? n.shortLabel : n.label;
      const w = g.measureText(text).width;
      const box: LabelBox = { x0: sx - w / 2 - 3, y0: sy + 3, x1: sx + w / 2 + 3, y1: sy + 19 };

      // Đỉnh đang chọn luôn được nhãn, kể cả khi phải đè lên đỉnh khác.
      if (!forced && overlaps(box)) return;
      plan.primary.add(n.id);
      boxes.push(box);

      if (n.tier !== 1 && n.kind !== "cluster" && !forced) return;
      const second = n.kind === "cluster" ? `${n.count} thực thể · rủi ro ${n.risk}` : `${n.role} · ${n.risk}`;
      g.font = "10px Geist, sans-serif";
      const w2 = g.measureText(second).width;
      const box2: LabelBox = { x0: sx - w2 / 2 - 3, y0: sy + 19, x1: sx + w2 / 2 + 3, y1: sy + 33 };
      if (!forced && overlaps(box2)) return;
      plan.secondary.add(n.id);
      boxes.push(box2);
    });

    return plan;
  }

  private drawColumns(g: CanvasRenderingContext2D): void {
    const seen = new Map<string, { x: number; y0: number; y1: number }>();
    let top = Infinity;
    let bottom = -Infinity;
    this.graph.nodes.forEach((n) => {
      const r = this.radiusOf(n);
      top = Math.min(top, n.y - r);
      bottom = Math.max(bottom, n.y + r);
      const cur = seen.get(n.stage);
      if (!cur) seen.set(n.stage, { x: n.x, y0: n.y, y1: n.y });
      else {
        cur.y0 = Math.min(cur.y0, n.y);
        cur.y1 = Math.max(cur.y1, n.y);
      }
    });
    if (seen.size < 2) return;

    const k = 1 / this.zoom;
    // Nhãn chặng phải nằm trên cả nhãn của đường bao cụm, nếu không hai hàng
    // chữ đè lên nhau ở những cột có cụm chạm mép trên.
    const hullTop = this.hulls.length ? Math.min(...this.hulls.map((h) => h.y0)) : Infinity;
    const labelY = Math.min(top, hullTop) - 30 * k;
    g.textAlign = "center";
    g.textBaseline = "alphabetic";
    // Chữ thường và tương phản cao hơn bản trước: viết hoa toàn bộ ở cỡ nhỏ
    // với dấu tiếng Việt thì rất khó đọc, mà đây lại là hàng chữ giúp hiểu
    // pipeline nhanh nhất.
    g.font = `600 ${11.5 * k}px Geist, sans-serif`;

    // Bỏ qua nhãn nào sẽ đè lên nhãn trước đó: ở mức phóng thấp các cột sát
    // nhau và tám chữ dính thành một dòng không đọc được.
    let lastRight = -Infinity;
    const ordered = [...seen.entries()].sort((a, b) => a[1].x - b[1].x);

    ordered.forEach(([stage, pos]) => {
      const label = STAGE_LABEL[stage as keyof typeof STAGE_LABEL] ?? stage;
      const half = g.measureText(label).width / 2;
      if (pos.x - half < lastRight + 8 * k) return;
      lastRight = pos.x + half;
      g.fillStyle = "rgba(163,186,208,0.72)";
      g.fillText(label, pos.x, labelY);
      g.beginPath();
      g.moveTo(pos.x, labelY + 10 * k);
      g.lineTo(pos.x, bottom + 26 * k);
      g.strokeStyle = "rgba(133,173,209,0.07)";
      g.lineWidth = k;
      g.stroke();
    });
  }

  /**
   * Đường bao cụm.
   *
   * Phải đọc như một *vùng ngữ nghĩa*, không phải một cái thẻ giao diện: nền
   * rất nhạt, viền đứt mảnh, nhãn nằm ngoài phía trên. Đậm hơn mức này thì hull
   * sẽ cạnh tranh thị giác với chính các đỉnh nó bao.
   */
  private drawHulls(g: CanvasRenderingContext2D): void {
    const k = 1 / this.zoom;
    this.hulls.forEach((hull) => {
      const col = hull.negative ? C.inkDim : hull.risk >= 80 ? C.risk : C.primary;
      g.beginPath();
      roundRect(g, hull.x0, hull.y0, hull.x1 - hull.x0, hull.y1 - hull.y0, 24);
      g.fillStyle = withAlpha(col, hull.negative ? 0.03 : 0.055);
      g.fill();
      g.strokeStyle = withAlpha(col, hull.negative ? 0.14 : 0.26);
      g.lineWidth = 1.1 * k;
      g.setLineDash([8 * k, 7 * k]);
      g.stroke();
      g.setLineDash([]);

      g.textAlign = "left";
      g.textBaseline = "alphabetic";
      g.font = `600 ${10.5 * k}px Geist, sans-serif`;
      g.fillStyle = withAlpha(col, hull.negative ? 0.5 : 0.88);
      g.fillText(hull.label.toUpperCase(), hull.x0 + 12 * k, hull.y0 - 9 * k);

      g.font = `${9.5 * k}px "JetBrains Mono", monospace`;
      g.fillStyle = withAlpha(C.inkLow, 0.75);
      const w = g.measureText(`${hull.total}`).width;
      g.fillText(`×${hull.total}`, hull.x1 - 12 * k - w, hull.y0 - 9 * k);
    });
  }

  private edgeAlphaWidth(e: RenderEdge): { alpha: number; width: number; level: number } {
    const lvl = this.emphasis?.edgeLevel.get(e.id) ?? 3;
    const style = EDGE_LEVEL[lvl];
    let width = style.width;
    // Cạnh tiền dày theo log giá trị, nhưng không vượt trần của tầng.
    if (e.money && e.amt != null) {
      width = Math.max(style.width * 0.75, Math.min(style.width * 1.35, Math.log10(1 + e.amt) * 0.62));
    }
    if (e.count > 1) width *= 1.15;
    return { alpha: style.alpha, width, level: lvl };
  }

  private drawEdges(g: CanvasRenderingContext2D): void {
    const hidden = this.emphasis?.hidden;
    const perf = this.opts.perf;

    // Vẽ tầng thấp trước để đường tiền chính luôn nằm trên cùng.
    const ordered = [...this.graph.edges].sort(
      (a, b) => (this.emphasis?.edgeLevel.get(b.id) ?? 3) - (this.emphasis?.edgeLevel.get(a.id) ?? 3),
    );

    ordered.forEach((e) => {
      const a = this.graph.byId[e.s];
      const b = this.graph.byId[e.t];
      if (!a || !b) return;
      if (hidden?.has(e.s) || hidden?.has(e.t)) return;

      const { alpha, width, level } = this.edgeAlphaWidth(e);
      if (perf && level === 4) return;

      const isSel = this.selectedEdgeId === e.id;
      const isHov = this.hoverEdgeId === e.id;
      const negative = a.negative || b.negative;
      // Đường tiền chính lấy màu theo chặng của đỉnh đích: càng gần ví operator
      // càng nóng, nên nhìn một cái là biết khúc nào của quá trình rửa.
      const col =
        level === 1 && !isSel
          ? pathStageColor(b.stage)
          : edgeColor({ onPath: false, selected: isSel, inferred: e.inferred, money: e.money, negative });

      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1;
      const ux = dx / d;
      const uy = dy / d;
      const ra = this.radiusOf(a) + 4;
      const rb = this.radiusOf(b) + 10;
      const x1 = a.x + ux * ra;
      const y1 = a.y + uy * ra;
      const x2 = b.x - ux * rb;
      const y2 = b.y - uy * rb;

      g.globalAlpha = isSel || isHov ? 1 : alpha;
      g.strokeStyle = col;
      g.lineWidth = isSel ? width + 1 : width;
      g.setLineDash(e.inferred ? [6, 5] : e.layer === "device" ? [2, 4] : []);

      g.beginPath();
      if (level <= 2 && !perf) {
        // Cạnh chính vẽ cong nhẹ: đường thẳng chồng nhau khi nhiều cạnh cùng
        // chạy giữa hai cột, cong một chút là tách ra ngay.
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2 - Math.min(26, d * 0.08);
        g.moveTo(x1, y1);
        g.quadraticCurveTo(mx, my, x2, y2);
      } else {
        g.moveTo(x1, y1);
        g.lineTo(x2, y2);
      }
      g.stroke();
      g.setLineDash([]);

      if (e.money && level <= 3) {
        g.beginPath();
        g.moveTo(x2, y2);
        g.lineTo(x2 - ux * 9 - uy * 4.2, y2 - uy * 9 + ux * 4.2);
        g.lineTo(x2 - ux * 9 + uy * 4.2, y2 - uy * 9 - ux * 4.2);
        g.closePath();
        g.fillStyle = col;
        g.fill();
      }

      // Số tiền chỉ hiện trên đường tiền đang xem, cạnh đang chọn hoặc đang rê
      // chuột. Rải số lên mọi cạnh thì ba mươi mấy con số cùng lúc trở thành
      // nhiễu, và chính con số trên đường chính lại chìm mất.
      const wantLabel = !perf && e.label && (isSel || isHov || level === 1);
      if (wantLabel) {
        const k = 1 / this.zoom;
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        g.globalAlpha = 1;
        g.font = `${9.5 * k}px Geist, sans-serif`;
        g.textAlign = "center";
        g.textBaseline = "alphabetic";
        const tw = g.measureText(e.label).width;
        g.fillStyle = "rgba(5,11,18,0.88)";
        g.fillRect(mx - tw / 2 - 4 * k, my - 15 * k, tw + 8 * k, 14 * k);
        g.fillStyle = e.inferred ? C.agentSoft : level === 1 ? C.riskSoft : C.inkSoft;
        g.fillText(e.label, mx, my - 5 * k);
      }
      g.globalAlpha = 1;
    });
  }

  /**
   * Vẽ chỗ đứt bằng chứng.
   *
   * Cố tình không giống bất kỳ cạnh nào: chấm rời, màu trung tính, không mũi
   * tên dòng tiền, và có dấu hỏi ở giữa. Người xem phải đọc ra ngay rằng đây là
   * chỗ *chưa chứng minh được*, chứ không phải một quan hệ yếu.
   */
  private drawGaps(g: CanvasRenderingContext2D): void {
    if (!this.gaps.length) return;
    const k = 1 / this.zoom;

    this.gaps.forEach((rg) => {
      const a = this.graph.byId[rg.fromId];
      const b = this.graph.byId[rg.toId];
      if (!a || !b) return;
      if (this.emphasis?.hidden.has(rg.fromId) || this.emphasis?.hidden.has(rg.toId)) return;

      const hovered = this.hoverGapId === rg.id;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1;
      const ux = dx / d;
      const uy = dy / d;
      const x1 = a.x + ux * (this.radiusOf(a) + 6);
      const y1 = a.y + uy * (this.radiusOf(a) + 6);
      const x2 = b.x - ux * (this.radiusOf(b) + 6);
      const y2 = b.y - uy * (this.radiusOf(b) + 6);

      g.globalAlpha = hovered ? 1 : 0.62;
      g.strokeStyle = C.inkSoft;
      g.lineWidth = (hovered ? 2 : 1.5) * k;
      g.setLineDash([2 * k, 6 * k]);
      g.beginPath();
      g.moveTo(x1, y1);
      g.lineTo(x2, y2);
      g.stroke();
      g.setLineDash([]);

      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;

      g.beginPath();
      g.arc(mx, my, 9 * k, 0, Math.PI * 2);
      g.fillStyle = C.app;
      g.fill();
      g.strokeStyle = C.inkSoft;
      g.lineWidth = 1.2 * k;
      g.stroke();
      g.fillStyle = C.inkSoft;
      g.font = `700 ${10 * k}px Geist, sans-serif`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText("?", mx, my + 0.5 * k);

      if (this.level !== "far" || hovered) {
        g.font = `${9.5 * k}px Geist, sans-serif`;
        g.textBaseline = "alphabetic";
        const label = "Thiếu liên kết quan sát";
        const tw = g.measureText(label).width;
        g.fillStyle = "rgba(5,11,18,0.9)";
        g.fillRect(mx - tw / 2 - 4 * k, my - 30 * k, tw + 8 * k, 14 * k);
        g.fillStyle = C.inkSoft;
        g.fillText(label, mx, my - 20 * k);
      }
      g.globalAlpha = 1;
    });
  }

  /** Chỗ đứt gần con trỏ nhất, dùng cho tooltip. */
  private gapAt(px: number, py: number): RenderGap | null {
    let best = 10;
    let hit: RenderGap | null = null;
    this.gaps.forEach((rg) => {
      const a = this.graph.byId[rg.fromId];
      const b = this.graph.byId[rg.toId];
      if (!a || !b) return;
      const ax = a.x * this.zoom + this.panX;
      const ay = a.y * this.zoom + this.panY;
      const bx = b.x * this.zoom + this.panX;
      const by = b.y * this.zoom + this.panY;
      for (let i = 0; i <= 16; i++) {
        const t = i / 16;
        const d = Math.hypot(ax + (bx - ax) * t - px, ay + (by - ay) * t - py);
        if (d < best) {
          best = d;
          hit = rg;
        }
      }
    });
    return hit;
  }

  private radiusOf(n: RenderNode): number {
    return nodeRadius(n.tier, n.kind === "cluster", n.count);
  }

  private drawNodes(g: CanvasRenderingContext2D): void {
    const hidden = this.emphasis?.hidden;

    this.graph.nodes.forEach((n) => {
      if (hidden?.has(n.id)) return;
      const target = this.emphasis?.nodeAlpha.get(n.id) ?? 1;
      const alpha = this.stepAlpha(n.id, target);
      if (alpha < 0.02) return;

      const st = typeStyle(n.type);
      const isSel = this.selectedNodeId === n.id;
      const isHov = this.hoverId === n.id;
      // Đỉnh đang chọn to thêm 10% — đủ để mắt bắt được mà không xô lệch bố cục.
      const r = this.radiusOf(n) * (isSel ? 1.1 : 1);

      g.globalAlpha = alpha;

      // Vòng rủi ro: dùng độ dày + vòng ngoài, không chỉ dựa vào màu.
      if (n.risk >= 80) {
        g.beginPath();
        g.arc(n.x, n.y, r + 7, 0, Math.PI * 2);
        g.strokeStyle = withAlpha(C.risk, 0.5);
        g.lineWidth = 1.4;
        g.setLineDash([3, 3]);
        g.stroke();
        g.setLineDash([]);
      } else if (n.risk >= 60) {
        g.beginPath();
        g.arc(n.x, n.y, r + 6, 0, Math.PI * 2);
        g.strokeStyle = withAlpha(C.warn, 0.38);
        g.lineWidth = 1;
        g.setLineDash([2, 4]);
        g.stroke();
        g.setLineDash([]);
      }

      if (isSel) {
        g.beginPath();
        g.arc(n.x, n.y, r + 11, 0, Math.PI * 2);
        g.strokeStyle = withAlpha(C.primary, 0.8);
        g.lineWidth = 1.6;
        g.stroke();
      }

      // Cụm vẽ hai lớp lệch nhau để nhìn ra ngay là "nhiều thực thể".
      if (n.kind === "cluster") {
        drawShape(g, st.shape, n.x + 4, n.y + 4, r);
        g.fillStyle = withAlpha(st.color, 0.1);
        g.fill();
        g.strokeStyle = withAlpha(st.color, 0.35);
        g.lineWidth = 1;
        g.stroke();
      }

      drawShape(g, st.shape, n.x, n.y, r);
      g.fillStyle = n.negative ? "#0B1A16" : C.panel;
      g.fill();
      g.strokeStyle = n.negative ? withAlpha(C.inkLow, 0.7) : st.color;
      g.lineWidth = isSel ? 2.8 : n.risk >= 80 ? 2.2 : n.risk >= 60 ? 1.7 : 1.2;
      if (isSel && !this.opts.perf) {
        g.save();
        g.shadowColor = st.color;
        g.shadowBlur = 14;
        g.stroke();
        g.restore();
      } else {
        g.stroke();
      }

      if (st.shape === "diamond2") {
        drawShape(g, "diamond", n.x, n.y, r * 0.7);
        g.strokeStyle = withAlpha(st.color, 0.6);
        g.lineWidth = 1;
        g.stroke();
      }

      g.fillStyle = n.negative ? C.inkLow : st.color;
      g.font = `600 ${Math.round(r * 0.72)}px "JetBrains Mono", monospace`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(n.kind === "cluster" ? String(n.count) : st.glyph, n.x, n.y + 0.5);

      // Chỉ báo mức độ, đặt góc trên phải.
      if (n.risk >= 60 && n.kind === "node") {
        const bx = n.x + r * 0.92;
        const by = n.y - r * 0.92;
        g.beginPath();
        g.arc(bx, by, 6.2, 0, Math.PI * 2);
        g.fillStyle = n.risk >= 80 ? C.risk : C.warn;
        g.fill();
        g.fillStyle = C.app;
        g.font = '700 8px "JetBrains Mono", monospace';
        g.fillText(n.risk >= 80 ? "!" : "▲", bx, by + 0.4);
      }

      if (n.negative) {
        const bx = n.x - r * 0.92;
        const by = n.y - r * 0.92;
        g.beginPath();
        g.arc(bx, by, 5.8, 0, Math.PI * 2);
        g.fillStyle = C.ok;
        g.fill();
        g.fillStyle = C.app;
        g.font = '700 8px "JetBrains Mono", monospace';
        g.fillText("✓", bx, by + 0.4);
      }

      this.drawNodeLabel(g, n, r, alpha, isSel || isHov);
      g.globalAlpha = 1;
    });
  }

  /**
   * Semantic zoom: mức chi tiết của nhãn phụ thuộc mức phóng.
   *
   * Ở xa chỉ hiện tên cụm và các đỉnh tier 1 — đúng chỗ analyst cần để nhận ra
   * hình dạng vụ việc. Mã kỹ thuật (số tài khoản, địa chỉ ví) chỉ xuất hiện khi
   * đã phóng đủ gần để thực sự đọc chúng.
   */
  private drawNodeLabel(
    g: CanvasRenderingContext2D,
    n: RenderNode,
    r: number,
    alpha: number,
    forced: boolean,
  ): void {
    if (this.opts.perf && !forced) return;
    if (!this.labelPlan.primary.has(n.id) && !forced) return;

    const lvl = this.level;

    // Chữ vẽ trong hệ toạ độ world nên bị nhân với mức phóng. Chia ngược lại
    // để cỡ chữ trên màn hình luôn cố định — nhãn đọc được ở mọi mức phóng,
    // thay vì teo lại cùng đồ thị như bản trước.
    const k = 1 / this.zoom;
    g.textAlign = "center";
    g.textBaseline = "alphabetic";

    const primary = lvl === "far" ? n.shortLabel : n.label;
    const size = n.tier === 1 ? 13 : n.tier === 2 ? 12 : 10.5;
    g.font = `${n.tier === 1 ? "600" : "500"} ${size * k}px Geist, sans-serif`;
    g.fillStyle = withAlpha(C.inkHi, Math.min(1, alpha * 0.96));
    g.fillText(primary, n.x, n.y + r + 15 * k);

    if (lvl === "far") return;

    // Dòng phụ chỉ vẽ khi lượt chống chồng đã cấp chỗ cho nó.
    if (this.labelPlan.secondary.has(n.id) || forced) {
      const second = n.kind === "cluster" ? `${n.count} thực thể · rủi ro ${n.risk}` : `${n.role} · ${n.risk}`;
      g.font = `${10 * k}px Geist, sans-serif`;
      g.fillStyle = withAlpha(n.risk >= 80 ? C.riskSoft : C.inkLow, alpha);
      g.fillText(second, n.x, n.y + r + 28 * k);
    }

    if (lvl !== "close" && !forced) return;

    // Mức gần: mã kỹ thuật và số tiền.
    if (n.sub) {
      g.font = `${9 * k}px "JetBrains Mono", monospace`;
      g.fillStyle = withAlpha(C.inkDim, alpha);
      g.fillText(n.sub, n.x, n.y + r + 41 * k);
    }
    if (n.ref && (n.ref.inUsd > 0 || n.ref.outUsd > 0)) {
      g.font = `${9 * k}px "JetBrains Mono", monospace`;
      g.fillStyle = withAlpha(C.primary, alpha * 0.9);
      g.fillText(compactUsd(Math.max(n.ref.inUsd, n.ref.outUsd)), n.x, n.y + r + 53 * k);
    }
  }

  private drawMinimap(g: CanvasRenderingContext2D): void {
    const mw = 124;
    const mh = 78;
    const mx = this.w - mw - 12;
    const my = this.h - mh - 12;
    const vis = this.graph.nodes.filter((n) => !this.emphasis?.hidden.has(n.id));
    if (!vis.length) return;

    const xs = vis.map((n) => n.x);
    const ys = vis.map((n) => n.y);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys);
    const k = Math.min((mw - 14) / (x1 - x0 || 1), (mh - 14) / (y1 - y0 || 1));

    g.globalAlpha = 0.82;
    g.beginPath();
    roundRect(g, mx, my, mw, mh, 9);
    g.fillStyle = "rgba(7,17,28,0.86)";
    g.fill();
    g.strokeStyle = "rgba(133,173,209,0.14)";
    g.lineWidth = 1;
    g.stroke();
    g.globalAlpha = 1;

    vis.forEach((n) => {
      const px = mx + 7 + (n.x - x0) * k;
      const py = my + 7 + (n.y - y0) * k;
      const a = this.emphasis?.nodeAlpha.get(n.id) ?? 1;
      g.globalAlpha = Math.max(0.25, a);
      g.fillStyle = n.risk >= 80 ? C.risk : n.risk >= 60 ? C.warn : "#3A6E8A";
      g.fillRect(px - 1.1, py - 1.1, 2.4, 2.4);
    });
    g.globalAlpha = 1;

    const vx0 = -this.panX / this.zoom;
    const vy0 = -this.panY / this.zoom;
    const rx = mx + 7 + (vx0 - x0) * k;
    const ry = my + 7 + (vy0 - y0) * k;
    const rw = (this.w / this.zoom) * k;
    const rh = (this.h / this.zoom) * k;
    g.strokeStyle = withAlpha(C.primary, 0.65);
    g.lineWidth = 1;
    g.strokeRect(
      Math.max(mx + 2, rx),
      Math.max(my + 2, ry),
      Math.min(mw - 4, rw),
      Math.min(mh - 4, rh),
    );
  }

  // ===== hit test =====

  private toLocal(ev: PointerEvent | MouseEvent | WheelEvent): { x: number; y: number } {
    const rect = this.canvas.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  }

  private nodeAt(px: number, py: number): { node: RenderNode | null; dist: number } {
    let best = Infinity;
    let hit: RenderNode | null = null;
    this.graph.nodes.forEach((n) => {
      if (this.emphasis?.hidden.has(n.id)) return;
      if ((this.emphasis?.nodeAlpha.get(n.id) ?? 1) < 0.05) return;
      const sx = n.x * this.zoom + this.panX;
      const sy = n.y * this.zoom + this.panY;
      const lim = Math.max(10, (this.radiusOf(n) + 6) * this.zoom);
      const d = Math.hypot(sx - px, sy - py);
      if (d <= lim && d < best) {
        best = d;
        hit = n;
      }
    });
    return { node: hit, dist: best };
  }

  private edgeAt(px: number, py: number): { edge: RenderEdge | null; dist: number } {
    let best = Infinity;
    let hit: RenderEdge | null = null;
    this.graph.edges.forEach((e) => {
      const a = this.graph.byId[e.s];
      const b = this.graph.byId[e.t];
      if (!a || !b) return;
      if (this.emphasis?.hidden.has(e.s) || this.emphasis?.hidden.has(e.t)) return;
      const ax = a.x * this.zoom + this.panX;
      const ay = a.y * this.zoom + this.panY;
      const bx = b.x * this.zoom + this.panX;
      const by = b.y * this.zoom + this.panY;
      for (let i = 0; i <= 16; i++) {
        const t = i / 16;
        const x = ax + (bx - ax) * t;
        const y = ay + (by - ay) * t;
        const d = Math.hypot(x - px, y - py);
        if (d < best) {
          best = d;
          hit = e;
        }
      }
    });
    return { edge: best <= 9 ? hit : null, dist: best };
  }

  private bindEvents(): void {
    const el = this.canvas;
    let drag: { x: number; y: number; panX: number; panY: number } | null = null;
    let moved = false;

    el.addEventListener("pointerdown", (ev) => {
      el.setPointerCapture(ev.pointerId);
      moved = false;
      drag = { x: ev.clientX, y: ev.clientY, panX: this.panX, panY: this.panY };
      this.host.style.cursor = "grabbing";
    });

    el.addEventListener("pointermove", (ev) => {
      if (drag) {
        if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3) moved = true;
        this.panX = drag.panX + (ev.clientX - drag.x);
        this.panY = drag.panY + (ev.clientY - drag.y);
        this.invalidate();
        return;
      }
      this.handleHover(ev);
    });

    el.addEventListener("pointerup", (ev) => {
      this.host.style.cursor = "grab";
      const wasDrag = moved;
      drag = null;
      if (wasDrag) return;
      const { x, y } = this.toLocal(ev);
      const nh = this.nodeAt(x, y);
      const eh = this.edgeAt(x, y);
      if (nh.node && (!eh.edge || nh.dist <= eh.dist + 2)) {
        this.cb.onSelectNode?.(nh.node.id);
      } else if (eh.edge) {
        this.cb.onSelectEdge?.(eh.edge.id);
      } else {
        this.cb.onSelectNode?.(null);
      }
    });

    el.addEventListener("dblclick", (ev) => {
      const { x, y } = this.toLocal(ev);
      const nh = this.nodeAt(x, y);
      if (nh.node) this.cb.onExpandNode?.(nh.node.id);
    });

    el.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        const { x, y } = this.toLocal(ev);
        const factor = ev.deltaY < 0 ? 1.12 : 0.89;
        const nz = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, this.zoom * factor));
        const s = nz / this.zoom;
        this.panX = x - (x - this.panX) * s;
        this.panY = y - (y - this.panY) * s;
        this.zoom = nz;
        this.emitZoom();
        this.invalidate();
      },
      { passive: false },
    );

    el.addEventListener("mouseleave", () => {
      this.tooltip.style.display = "none";
      this.hoverId = null;
      this.hoverEdgeId = null;
      this.cb.onHover?.(null);
      this.invalidate();
    });
  }

  private handleHover(ev: PointerEvent): void {
    const { x, y } = this.toLocal(ev);
    const nh = this.nodeAt(x, y);
    const eh = nh.node ? { edge: null as RenderEdge | null } : this.edgeAt(x, y);
    const gh = nh.node || eh.edge ? null : this.gapAt(x, y);
    const nodeId = nh.node?.id ?? null;
    const edgeId = eh.edge?.id ?? null;
    const gapId = gh?.id ?? null;

    if (nodeId !== this.hoverId || edgeId !== this.hoverEdgeId || gapId !== this.hoverGapId) {
      this.hoverId = nodeId;
      this.hoverEdgeId = edgeId;
      this.hoverGapId = gapId;
      this.cb.onHover?.(nodeId);
      this.invalidate();
    }

    this.host.style.cursor = nodeId || edgeId || gapId ? "pointer" : "grab";

    const n = nh.node as RenderNode | null;
    const e = eh.edge;
    if (!n && !e && !gh) {
      this.tooltip.style.display = "none";
      return;
    }

    if (gh) {
      const from = this.graph.byId[gh.fromId];
      const to = this.graph.byId[gh.toId];
      this.tooltip.innerHTML =
        `<b style="color:${C.inkSoft}">Thiếu liên kết quan sát</b>` +
        `<br><span style="color:${C.inkMid}">${escapeHtml(from?.label ?? "")} → ${escapeHtml(to?.label ?? "")}</span>` +
        `<br><br><span style="color:${C.inkLow}">Đã biết:</span> ${escapeHtml(gh.gap.known)}` +
        `<br><span style="color:${C.inkLow}">Còn thiếu:</span> ${escapeHtml(gh.gap.missing)}` +
        `<br><span style="color:${C.inkLow}">Nguồn có thể lấp:</span> ${escapeHtml(gh.gap.suggestion)}` +
        `<br><br><span style="color:${C.warnSoft};font-size:10px">Đây là ghi chú điều tra, không phải một quan hệ. Không được dùng như bằng chứng.</span>`;
    }

    if (n) {
      const st = typeStyle(n.type);
      const flow =
        n.ref && (n.ref.inUsd > 0 || n.ref.outUsd > 0)
          ? `<br><span style="color:${C.inkLow}">Vào</span> <b style="font-family:'JetBrains Mono',monospace">${compactUsd(
              n.ref.inUsd,
            )}</b> · <span style="color:${C.inkLow}">Ra</span> <b style="font-family:'JetBrains Mono',monospace">${compactUsd(
              n.ref.outUsd,
            )}</b>`
          : "";
      this.tooltip.innerHTML =
        `<b>${escapeHtml(n.label)}</b> <span style="color:${C.inkLow}">· ${st.name}</span>` +
        (n.kind === "cluster" ? `<br><span style="color:${C.primary}">Bấm để mở cụm ${n.count} thực thể</span>` : "") +
        (n.sub ? `<br><span style="color:${C.inkSoft}">${escapeHtml(n.sub)}</span>` : "") +
        `<br>Rủi ro <b style="font-family:'JetBrains Mono',monospace;color:${
          n.risk >= 80 ? C.risk : n.risk >= 60 ? C.warn : C.ok
        }">${n.risk}</b>` +
        flow +
        (n.ref ? `<br><span style="color:${C.inkLow}">Bậc đỉnh</span> ${n.ref.degree}` : "") +
        (n.negative ? `<br><span style="color:${C.okSoft};font-size:10px">đối chứng hợp pháp</span>` : "");
    } else if (e) {
      const a = this.graph.byId[e.s];
      const b = this.graph.byId[e.t];
      this.tooltip.innerHTML =
        `<b>${escapeHtml(a?.label ?? "")} → ${escapeHtml(b?.label ?? "")}</b>` +
        (e.label ? `<br><span style="color:${C.inkSoft}">${escapeHtml(e.label)}</span>` : "") +
        (e.count > 1 ? `<br><span style="color:${C.inkLow}">gộp ${e.count} quan hệ</span>` : "") +
        (e.inferred
          ? `<br><span style="color:${C.agentSoft};font-size:10px">SUY LUẬN · tin cậy ${
              e.conf != null ? e.conf.toFixed(2) : "—"
            }</span>`
          : "");
    }

    const rect = this.host.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    this.tooltip.style.display = "block";
    const tw = this.tooltip.offsetWidth;
    let lx = mx + 16;
    if (lx + tw > rect.width - 6) lx = mx - tw - 16;
    this.tooltip.style.left = `${Math.max(4, lx)}px`;
    this.tooltip.style.top = `${Math.max(4, Math.min(rect.height - 70, my - 14))}px`;
  }
}

// ===== helpers =====

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  g.moveTo(x + r, y);
  g.lineTo(x + w - r, y);
  g.quadraticCurveTo(x + w, y, x + w, y + r);
  g.lineTo(x + w, y + h - r);
  g.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  g.lineTo(x + r, y + h);
  g.quadraticCurveTo(x, y + h, x, y + h - r);
  g.lineTo(x, y + r);
  g.quadraticCurveTo(x, y, x + r, y);
  g.closePath();
}

function drawShape(g: CanvasRenderingContext2D, shape: ShapeKind, x: number, y: number, r: number): void {
  g.beginPath();
  switch (shape) {
    case "rect":
      g.rect(x - r * 1.15, y - r * 0.78, r * 2.3, r * 1.56);
      break;
    case "rrect":
      roundRect(g, x - r * 1.1, y - r * 0.75, r * 2.2, r * 1.5, r * 0.34);
      break;
    case "pill":
      roundRect(g, x - r * 1.15, y - r * 0.68, r * 2.3, r * 1.36, r * 0.68);
      break;
    case "diamond":
    case "diamond2":
      g.moveTo(x, y - r * 1.25);
      g.lineTo(x + r * 1.15, y);
      g.lineTo(x, y + r * 1.25);
      g.lineTo(x - r * 1.15, y);
      g.closePath();
      break;
    case "hex":
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 6 + (i * Math.PI) / 3;
        const px = x + Math.cos(a) * r * 1.15;
        const py = y + Math.sin(a) * r * 1.15;
        if (i) g.lineTo(px, py);
        else g.moveTo(px, py);
      }
      g.closePath();
      break;
    case "octagon":
      for (let i = 0; i < 8; i++) {
        const a = Math.PI / 8 + (i * Math.PI) / 4;
        const px = x + Math.cos(a) * r * 1.2;
        const py = y + Math.sin(a) * r * 1.2;
        if (i) g.lineTo(px, py);
        else g.moveTo(px, py);
      }
      g.closePath();
      break;
    case "warning":
      g.moveTo(x, y - r * 1.2);
      g.lineTo(x + r * 1.15, y + r * 0.85);
      g.lineTo(x - r * 1.15, y + r * 0.85);
      g.closePath();
      break;
    case "container":
      roundRect(g, x - r * 1.35, y - r * 0.85, r * 2.7, r * 1.7, r * 0.28);
      break;
    case "circle":
    default:
      g.arc(x, y, r, 0, Math.PI * 2);
  }
}

/** Ghép alpha vào màu hex hoặc rgba của palette. */
function withAlpha(color: string, alpha: number): string {
  if (color.startsWith("rgba")) return color.replace(/[\d.]+\)$/, `${alpha})`);
  const hex = color.replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function compactUsd(v: number): string {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3)}K`;
  return `$${Math.round(v)}`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c);
}
