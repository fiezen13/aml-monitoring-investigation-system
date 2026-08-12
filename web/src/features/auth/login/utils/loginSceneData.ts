/**
 * Dữ liệu hình học của quả cầu mạng lưới ở màn đăng nhập.
 *
 * Sinh một lần, không đổi theo khung hình — engine chỉ xoay và chiếu lại. Tách
 * ra khỏi component để phần vẽ không phải bận tâm tới việc dựng hình, và để
 * cùng một cấu hình dùng được cho cả bản tĩnh khi người dùng tắt hiệu ứng.
 */

export interface ScenePoint {
  x: number;
  y: number;
  z: number;
  /** Bán kính vẽ tương đối. */
  size: number;
  /** Lệch pha nhấp nháy, để các điểm không đập cùng nhịp. */
  phase: number;
  /** Điểm cảnh báo — vẽ đỏ, đập chậm. */
  alert: boolean;
}

export interface SceneLink {
  a: number;
  b: number;
  /** Độ đậm cơ sở, suy từ khoảng cách. */
  weight: number;
}

export interface SceneArc {
  a: number;
  b: number;
  /** Độ cao vồng lên khỏi mặt cầu. */
  lift: number;
  /** Lệch pha của chấm chạy. */
  offset: number;
}

export interface SceneData {
  points: ScenePoint[];
  links: SceneLink[];
  arcs: SceneArc[];
}

/**
 * Bộ sinh số giả ngẫu nhiên có hạt giống.
 *
 * Cần tất định: quả cầu phải giống hệt nhau giữa các lần tải, nếu không mỗi lần
 * vào trang đăng nhập lại thấy một mạng lưới khác — trông như dữ liệu thật đang
 * đổi, mà nó không phải.
 */
function seeded(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/** Phân bố điểm đều trên mặt cầu theo xoắn ốc Fibonacci. */
function fibonacciSphere(count: number, rand: () => number): ScenePoint[] {
  const points: ScenePoint[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    points.push({
      x: Math.cos(theta) * radius,
      y,
      z: Math.sin(theta) * radius,
      size: 0.7 + rand() * 0.9,
      phase: rand() * Math.PI * 2,
      alert: false,
    });
  }
  return points;
}

const NODE_COUNT = 108;
const MAX_LINKS = 58;
const ARC_COUNT = 4;
const ALERT_COUNT = 2;

export function buildSceneData(): SceneData {
  const rand = seeded(20260812);
  const points = fibonacciSphere(NODE_COUNT, rand);

  // Hai điểm cảnh báo đặt lệch nhau để không bao giờ cùng khuất mặt sau.
  const alertIdx = [Math.floor(NODE_COUNT * 0.22), Math.floor(NODE_COUNT * 0.68)];
  alertIdx.slice(0, ALERT_COUNT).forEach((i) => {
    points[i].alert = true;
    points[i].size = 1.5;
  });

  // Nối các cặp gần nhau: cho ra lưới trông như mạng lưới quan hệ chứ không
  // phải một mớ dây nối ngẫu nhiên xuyên qua tâm cầu.
  const candidates: SceneLink[] = [];
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      const a = points[i];
      const b = points[j];
      const d = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
      if (d < 0.46) candidates.push({ a: i, b: j, weight: 1 - d / 0.46 });
    }
  }
  candidates.sort((p, q) => q.weight - p.weight);
  const links = candidates.slice(0, MAX_LINKS);

  // Cung giao dịch: nối hai điểm ở xa nhau, vồng lên khỏi mặt cầu.
  const arcs: SceneArc[] = [];
  for (let k = 0; k < ARC_COUNT; k++) {
    const a = Math.floor(rand() * points.length);
    let b = Math.floor(rand() * points.length);
    if (b === a) b = (b + 7) % points.length;
    arcs.push({ a, b, lift: 0.28 + rand() * 0.22, offset: rand() });
  }
  // Một cung luôn kết thúc ở điểm cảnh báo — đó là câu chuyện của màn hình này.
  arcs[0] = { a: Math.floor(NODE_COUNT * 0.5), b: alertIdx[0], lift: 0.34, offset: 0.15 };

  return { points, links, arcs };
}
