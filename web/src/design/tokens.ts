/**
 * Token nguyên thuỷ của F7 Financial Intelligence Console.
 *
 * Đây là tầng thấp nhất: giá trị thô, không mang ngữ nghĩa nghiệp vụ. Tầng trên
 * (`semantic.ts`, `risk.ts`, `visualization.ts`) mới quyết định "màu này nói
 * điều gì". Trang và component KHÔNG được đọc trực tiếp file này để tô màu ngữ
 * nghĩa — dùng `semantic.ts` hoặc `risk.ts`.
 *
 * Vì sao vẫn cần giá trị thô ở TypeScript trong khi đã có Tailwind: bốn engine
 * dựng hình (canvas tự viết, Cytoscape, MapLibre, Cesium) không đọc được class
 * CSS, chúng cần chuỗi hex. Đây là nguồn duy nhất cho cả hai thế giới —
 * `tailwind.config.js` import chính file này.
 */

/**
 * Năm tầng nền, xếp theo độ sâu thị giác.
 *
 * `panel` và `elev` được nâng nhẹ so với bản trước (#101820 → #111A24,
 * #15212B → #17242F): khoảng cách với `app` cũ chỉ khoảng 4 đơn vị luminance
 * nên thẻ nội dung gần như tan vào nền trang, và toàn bộ phân cấp phải gánh lên
 * vai đường viền. Nâng hai bậc này giữ nguyên identity tối-sâu nhưng cho panel
 * một chỗ đứng riêng. Ba tầng còn lại giữ nguyên.
 */
export const surface = {
  /** Nền ngoài cùng, cũng là nền của body. */
  app: "#080D12",
  /** Sidebar, header, thanh công cụ — tối hơn panel để khung đứng lùi lại. */
  side: "#0C131B",
  /** Thẻ nội dung. */
  panel: "#111A24",
  /** Hover của thẻ, hàng bảng, nền popover. */
  elev: "#17242F",
  /** Bề mặt nổi cao nhất: popover, modal, dropdown, command palette. */
  raised: "#1B2A36",
  /** Ô nhập liệu, select, nền lõm. */
  sunken: "#0A1017",
  /** Lớp phủ sau modal. */
  scrim: "rgba(4, 8, 12, 0.72)",
} as const;

/** Chữ — năm mức, dùng đúng thứ tự này cho phân cấp thông tin. */
export const ink = {
  hi: "#E6EDF3",
  mid: "#B6C4D0",
  soft: "#91A2B1",
  low: "#8397A8",
  dim: "#708597",
} as const;

/**
 * Đường kẻ. Màu đặc chứ không phải rgba: viền phải trông như nhau trên cả sáu
 * tầng nền, mà rgba thì đổi theo thứ nằm phía sau.
 */
export const line = {
  faint: "#141D26",
  soft: "#182430",
  base: "#1D2A35",
  strong: "#293B49",
  emphasis: "#385062",
} as const;

/**
 * Teal — accent duy nhất của hệ thống.
 *
 * Chỉ mang một nghĩa: đang chọn / focus / hành động chính / đang sống. Không
 * dùng cho "khối này bấm được", cho series biểu đồ, hay cho màu kênh dòng tiền.
 */
export const accent = {
  base: "#20C7A7",
  hover: "#2FDDBA",
  press: "#1BAF92",
  /** Nền của trạng thái đang chọn — đủ để thấy, không đủ để thành khối màu. */
  soft: "rgba(32, 199, 167, 0.10)",
  softer: "rgba(32, 199, 167, 0.06)",
  line: "rgba(32, 199, 167, 0.32)",
  /** Chữ đặt trên nền teal đặc. */
  on: "#04140F",
} as const;

/**
 * Sắc ngữ nghĩa. Mỗi sắc là một cặp `base`/`soft`: `base` cho viền, chấm, thanh
 * và nền tint; `soft` cho chữ đặt trên nền tint đó (base trên nền tối 10% không
 * đủ tương phản để đọc ở cỡ 11px).
 */
export const hue = {
  risk: { base: "#F45B69", soft: "#FF8792" },
  warn: { base: "#F0B44D", soft: "#F5CE8A" },
  ok: { base: "#4CC38A", soft: "#86DCB4" },
  info: { base: "#4B9EFF", soft: "#8CC0FF" },
  /** Hoạt động của tác tử AI và VASP. */
  agent: { base: "#A78BFA", soft: "#C9B8FC" },
  /** Kênh token / dự án tài sản số. */
  token: { base: "#F08A5C", soft: "#F7B394" },
} as const;

/**
 * Thang chữ.
 *
 * Bản trước nén tất cả vào 9.5–19px nên tiêu đề màn hình (17px) gần bằng nội
 * dung (12px). Bản này mở phần trên ra mà vẫn giữ phần dưới dày đặc cho bảng
 * biểu: console tài chính sống bằng mật độ, không phải bằng chữ to.
 */
export const fontSize = {
  micro: ["10px", "14px"],
  meta: ["11px", "15px"],
  data: ["12px", "16px"],
  body: ["13px", "18px"],
  bodyLg: ["14px", "20px"],
  h3: ["16px", "22px"],
  h2: ["20px", "27px"],
  h1: ["24px", "31px"],
} as const;

/**
 * Thang khoảng cách. Bội số của 4 với hai giá trị lẻ 6/10 dành riêng cho phần
 * trong của control — nút cao 28px không chia hết cho 8 mà vẫn phải cân.
 */
export const space = {
  0.5: "2px",
  1: "4px",
  1.5: "6px",
  2: "8px",
  2.5: "10px",
  3: "12px",
  4: "16px",
  5: "20px",
  6: "24px",
  8: "32px",
} as const;

/**
 * Bo góc. Console tài chính cần hình học tương đối chính xác — không nới lên
 * 16–24px cho mọi thẻ.
 */
export const radius = {
  chip: "20px",
  panel: "10px",
  control: "7px",
  sm: "5px",
} as const;

/**
 * Độ sâu.
 *
 * Panel và thẻ KHÔNG dùng shadow — độ sâu của chúng đến từ tầng nền và viền.
 * Shadow chỉ dành cho thứ thực sự nổi lên trên mặt phẳng nội dung.
 */
export const elevation = {
  popover: "0 12px 28px -12px rgba(0,0,0,0.65), 0 2px 6px -2px rgba(0,0,0,0.4)",
  modal: "0 32px 64px -24px rgba(0,0,0,0.8), 0 8px 16px -8px rgba(0,0,0,0.5)",
  /** Quầng rất nhẹ quanh phần tử đang được nhấn mạnh — không phải neon. */
  focus: "0 0 0 3px rgba(32, 199, 167, 0.16)",
} as const;

/** Thời lượng chuyển động, đơn vị giây (khớp API của Motion). */
export const duration = {
  instant: 0.08,
  fast: 0.14,
  normal: 0.22,
  slow: 0.36,
  spatial: 0.55,
} as const;

/** Đường cong easing, dạng cubic-bezier bốn số. */
export const easing = {
  standard: [0.2, 0, 0, 1],
  enter: [0, 0, 0.2, 1],
  exit: [0.4, 0, 1, 1],
} as const;

/** Ngăn xếp z-index — gom một chỗ để không còn `z-[9999]` rải rác. */
export const layer = {
  base: 0,
  overlayHud: 5,
  sticky: 10,
  dropdown: 40,
  drawer: 50,
  modal: 60,
  toast: 70,
} as const;
