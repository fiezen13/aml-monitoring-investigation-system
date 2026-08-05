/** @type {import('tailwindcss').Config} */
//
// Bảng màu lấy nguyên từ prototype "Financial City AML" (thư mục
// `Financial City AML Prototype/`). Tên token đặt theo vai trò chứ không theo
// màu, để đổi tông về sau không phải sửa từng chỗ dùng.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Nền — bốn tầng độ sâu, tối dần từ panel ra ngoài.
        app: "#050B12", // nền ngoài cùng, cũng là nền của body
        side: "#07111C", // sidebar, header, thanh công cụ
        panel: "#0D1C2A", // thẻ nội dung
        elev: "#112538", // trạng thái hover của thẻ và hàng bảng
        sunken: "#0A1724", // ô nhập liệu, select, nền lõm

        primary: {
          DEFAULT: "#12D6C5",
          hover: "#5FE8DB",
          soft: "rgba(18, 214, 197, 0.14)",
          line: "rgba(18, 214, 197, 0.45)",
        },

        // Đường kẻ. Prototype dùng đúng ba mức đậm nhạt.
        line: {
          DEFAULT: "rgba(133, 173, 209, 0.14)",
          soft: "rgba(133, 173, 209, 0.10)",
          faint: "rgba(133, 173, 209, 0.06)",
          strong: "rgba(133, 173, 209, 0.25)",
        },

        // Chữ — bốn mức, dùng đúng thứ tự này cho phân cấp thông tin.
        ink: {
          hi: "#E6F0F8", // tiêu đề, số liệu chính
          mid: "#B9C9D6", // nội dung thường
          soft: "#91A4B5", // nội dung phụ
          low: "#607487", // nhãn, chú thích
          dim: "#4A5D70", // nhãn nhóm viết hoa
        },

        // Ngữ nghĩa rủi ro. `risk` và `risk-soft` là cặp: nền đậm / chữ nhạt.
        risk: { DEFAULT: "#FF4D61", soft: "#FF6B7C" },
        warn: { DEFAULT: "#F5A524", soft: "#F5C97A" },
        ok: { DEFAULT: "#2DD4A7", soft: "#8FE8DF" },
        info: { DEFAULT: "#3185FF", soft: "#6FB0FF" },
        agent: { DEFAULT: "#A78BFA", soft: "#C9B8FC" }, // hoạt động của AI agent
        token: "#FF8A5C", // kênh token / dự án
      },

      fontFamily: {
        sans: ["Geist", "Inter", "system-ui", "-apple-system", "sans-serif"],
        // Mọi con số, mã định danh và hash dùng font đơn cách — bảng số liệu
        // chỉ đọc được khi các chữ số thẳng cột.
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },

      fontSize: {
        "3xs": ["9.5px", "13px"],
        "2xs": ["10.5px", "14px"],
        xs: ["11px", "15px"],
        sm: ["11.5px", "16px"],
        base: ["12px", "17px"],
        md: ["12.5px", "18px"],
        lg: ["13px", "19px"],
        xl: ["13.5px", "19px"],
        "2xl": ["15px", "21px"],
        "3xl": ["17px", "24px"],
        "4xl": ["19px", "26px"],
      },

      borderRadius: {
        panel: "12px",
        control: "8px",
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
