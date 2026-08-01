/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: "#071422",
        side: "#06111D",
        panel: "#0A1A29",
        elev: "#0D2031",
        primary: {
          DEFAULT: "#00B2A9",
          hover: "#13C6BD",
          soft: "rgba(0, 178, 169, 0.12)",
        },
        line: "rgba(148, 163, 184, 0.14)",
        ink: {
          hi: "#F1F5F9",
          mid: "#94A3B8",
          low: "#64748B",
        },
        risk: "#EF4444",
        warn: "#F59E0B",
        ok: "#22C55E",
        info: "#38BDF8",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      fontSize: {
        "2xs": ["11px", "14px"],
      },
      borderRadius: {
        panel: "8px",
        control: "6px",
      },
    },
  },
  plugins: [],
};
