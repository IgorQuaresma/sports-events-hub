import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand: deep teal-blue; all text/background pairs below meet WCAG AA contrast.
        brand: {
          50: "#eef7fb",
          100: "#d5ecf5",
          200: "#aedaea",
          300: "#77bfd8",
          500: "#1f8ab3",
          600: "#136f94",
          700: "#125a78",
          800: "#134a62",
          900: "#123d52",
        },
        accent: { 500: "#f97316", 600: "#ea580c" },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue",
          "Arial", "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.04), 0 1px 3px rgb(15 23 42 / 0.06)",
        lift: "0 4px 12px rgb(15 23 42 / 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
