/** @type {import('tailwindcss').Config} */
//
// FIN-07 Intelligence Dark.
//
// Tên token đặt theo vai trò chứ không theo màu, để đổi tông về sau không phải
// sửa từng chỗ dùng — và đó chính là điều đã xảy ra: bảng này thay thế bảng lấy
// từ prototype "Financial City AML", nơi mọi thứ đều là cyan #12D6C5.
//
// Hai luật màu của bộ này:
//
//  1. `primary` (teal) CHỈ mang một nghĩa: đang chọn / hành động chính / đang
//     sống. Không dùng nó cho "khối này bấm được", cho biểu đồ, hay cho màu
//     kênh — nếu teal ở khắp nơi thì nó không còn báo gì nữa.
//  2. Mức độ rủi ro có thang riêng và không trùng teal: ok xanh lá, info xanh
//     dương, warn hổ phách, risk đỏ. Bản cũ đặt ok = #2DD4A7, tức cũng là teal,
//     nên "bình thường" và "được chọn" nhìn như nhau.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Nền — năm tầng độ sâu. Khoảng cách giữa các tầng cố ý nhỏ: phân cấp
        // đến từ khoảng trắng và cỡ chữ, không phải từ độ tương phản nền.
        app: "#080D12", // nền ngoài cùng, cũng là nền của body
        side: "#0C131B", // sidebar, header, thanh công cụ
        panel: "#101820", // thẻ nội dung
        elev: "#15212B", // hover của thẻ, hàng bảng, popover
        sunken: "#0A1017", // ô nhập liệu, select, nền lõm

        primary: {
          DEFAULT: "#20C7A7",
          hover: "#2FDDBA",
          // Nền của trạng thái đang chọn. Đủ để thấy, không đủ để thành khối
          // màu — sidebar bản cũ dùng 0.14 và trông như một nút phát sáng.
          soft: "rgba(32, 199, 167, 0.10)",
          line: "rgba(32, 199, 167, 0.32)",
        },

        // Đường kẻ. Màu đặc chứ không phải rgba: viền phải trông như nhau trên
        // cả năm tầng nền, mà rgba thì đổi theo thứ nằm phía sau.
        line: {
          faint: "#141D26",
          soft: "#182430",
          DEFAULT: "#1D2A35",
          strong: "#293B49",
          emphasis: "#385062",
        },

        // Chữ — năm mức, dùng đúng thứ tự này cho phân cấp thông tin.
        ink: {
          hi: "#E6EDF3", // tiêu đề, số liệu chính
          mid: "#B6C4D0", // nội dung thường
          soft: "#91A2B1", // nội dung phụ
          low: "#8397A8", // nhãn, chú thích
          dim: "#708597", // nhãn nhóm viết hoa
        },

        // Ngữ nghĩa rủi ro. `x` và `x-soft` là cặp: nền/viền đậm, chữ nhạt.
        risk: { DEFAULT: "#F45B69", soft: "#FF8792" },
        warn: { DEFAULT: "#F0B44D", soft: "#F5CE8A" },
        ok: { DEFAULT: "#4CC38A", soft: "#86DCB4" },
        info: { DEFAULT: "#4B9EFF", soft: "#8CC0FF" },
        agent: { DEFAULT: "#A78BFA", soft: "#C9B8FC" }, // hoạt động của AI agent, VASP
        token: "#F08A5C", // kênh token / dự án
      },

      fontFamily: {
        sans: ["Geist", "Inter", "system-ui", "-apple-system", "sans-serif"],
        // Mọi con số, mã định danh và hash dùng font đơn cách — bảng số liệu
        // chỉ đọc được khi các chữ số thẳng cột.
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },

      // Thang chữ. Bản cũ nén tất cả vào 9.5–19px nên tiêu đề màn hình (17px)
      // gần bằng nội dung (12px) và không có phân cấp nào đọc được từ xa. Bản
      // này giữ nguyên phần dày đặc ở dưới cho bảng biểu, nhưng mở phần trên
      // ra để tiêu đề và số liệu chính có sức nặng.
      fontSize: {
        "3xs": ["10px", "13px"], // nhãn nhóm viết hoa
        "2xs": ["11px", "15px"], // metadata
        xs: ["11.5px", "16px"],
        sm: ["12px", "16px"],
        base: ["12.5px", "18px"], // điều hướng, nội dung bảng
        md: ["13px", "19px"], // nội dung thường
        lg: ["13.5px", "20px"],
        xl: ["14px", "20px"], // tiêu đề mục
        "2xl": ["16px", "22px"],
        "3xl": ["20px", "27px"], // tiêu đề màn hình
        "4xl": ["24px", "30px"], // số liệu KPI
      },

      borderRadius: {
        panel: "10px",
        control: "7px",
        chip: "20px",
      },

      keyframes: {
        // Nhịp đập của chỉ báo LIVE và các chấm trạng thái.
        fcPulse: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.3" } },
        // Chuyển màn hình: trôi lên 5px. Ngắn, không gây chờ đợi.
        fcUp: {
          from: { opacity: "0", transform: "translateY(5px)" },
          to: { opacity: "1", transform: "none" },
        },
      },
      animation: {
        pulse: "fcPulse 2.2s infinite",
        up: "fcUp 0.25s ease",
      },
    },
  },
  plugins: [],
};
