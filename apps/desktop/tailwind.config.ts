import type { Config } from "tailwindcss";
import tokens from "../../packages/design-tokens/tokens.json";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: tokens.color.bg,
        surface: tokens.color.surface,
        raised: tokens.color.surfaceRaised,
        line: tokens.color.line,
        ink: tokens.color.text,
        muted: tokens.color.textMuted,
        faint: tokens.color.textFaint,
        accent: tokens.color.accent,
        "accent-dim": tokens.color.accentDim,
        amber: tokens.color.amber,
        danger: tokens.color.danger,
        success: tokens.color.success,
        r0: tokens.color.risk.R0,
        r1: tokens.color.risk.R1,
        r2: tokens.color.risk.R2,
        r3: tokens.color.risk.R3,
      },
      fontFamily: {
        sans: tokens.font.sans.split(",").map((f) => f.trim()),
        mono: tokens.font.mono.split(",").map((f) => f.trim()),
      },
      borderRadius: {
        sm: tokens.radius.sm,
        md: tokens.radius.md,
        lg: tokens.radius.lg,
      },
    },
  },
  plugins: [],
} satisfies Config;
