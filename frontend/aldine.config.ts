import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#fafaf9", // stone-50
        bone: "#f5f5f4",   // stone-100
        ink: {
          base: "#1c1917", // stone-900
          muted: "#57534e", // stone-600
        },
        accent: "#A2574B", // terracotta
        hairline: "#e7e5e4", // stone-200
      },
      fontFamily: {
        display: ['var(--font-cinzel)', 'serif'],
        editorial: ['var(--font-eb-garamond)', 'serif'],
        interface: ['var(--font-inter)', 'sans-serif'],
        mono: ['var(--font-inter)', 'monospace'],
      },
      zIndex: {
        hide: '-1',
        base: '1',
        nav: '100',
        overlay: '1000',
      },
      spacing: {
        nav: '5rem', // 80px height for strict nav heights
      },
    },
  },
  plugins: [],
};
export default config;
