import type { Config } from "tailwindcss";

/**
 * The design system, such as it is.
 *
 * Deliberately small. A university portal earns credibility through
 * typography, spacing and restraint rather than through colour, so there are
 * two hues here and no more: a deep institutional navy that carries all the
 * structure, and a single muted gold used only where something must be
 * noticed. Everything else is a warm neutral.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0f2544",
          soft: "#33445e",
          muted: "#67748a",
        },
        navy: {
          50: "#f3f6fb",
          100: "#e3eaf5",
          200: "#c6d5e9",
          600: "#1d3f6e",
          700: "#173355",
          900: "#0f2544",
        },
        gold: {
          DEFAULT: "#a3771c",
          soft: "#f5ecd9",
        },
        paper: "#faf9f7",
        line: "#e6e2da",
      },
      fontFamily: {
        // No web fonts. A remote font is a build-time network dependency and a
        // render-blocking request, and the system serif stack below is a
        // genuinely good academic face on every platform the examiners will
        // open this on.
        serif: [
          "Iowan Old Style",
          "Palatino Linotype",
          "Palatino",
          "Georgia",
          "ui-serif",
          "serif",
        ],
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      fontSize: {
        display: ["clamp(2.25rem, 1.6rem + 2.4vw, 3.5rem)", { lineHeight: "1.08", letterSpacing: "-0.02em" }],
        title: ["clamp(1.6rem, 1.3rem + 1.1vw, 2.25rem)", { lineHeight: "1.15", letterSpacing: "-0.015em" }],
      },
      maxWidth: {
        prose: "68ch",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 37, 68, 0.04), 0 8px 24px -16px rgba(15, 37, 68, 0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
