/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#FBF7EF",
        forest: "#0C3B2E",
        leaf: "#1E7A4C",
        marigold: "#F2A33C",
        ink: "#1C2B22",
        muted: "#6C7B70",
        line: "#E7E0CC",
        mint: "#E8F6EC",
        sand: "#FDF3D7",
      },
      fontFamily: {
        display: ["Sora", "\"Hind Siliguri\"", "Inter", "sans-serif"],
        sans: ["\"Hind Siliguri\"", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(12,59,46,0.06), 0 8px 24px rgba(12,59,46,0.06)",
        lift: "0 12px 32px rgba(12,59,46,0.14)",
      },
    },
  },
  plugins: [],
};
