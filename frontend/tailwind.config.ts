/** @type {import('tailwindcss').Config} */
import { nextui } from "@nextui-org/react";

module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./node_modules/@nextui-org/theme/dist/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
      fontFamily: {
        display: ['var(--font-display)', 'Georgia', 'serif'],
        body: ['var(--font-inter)', 'sans-serif'],
      }
    },
  },
  darkMode: "class",
  plugins: [
    nextui({
      themes: {
        dark: {
          colors: {
            background: "#120E0F",
            foreground: "#F5F5F0",
            primary: {
              DEFAULT: "#E34234",
              foreground: "#F5F5F0",
            },
            secondary: {
              DEFAULT: "#D4AF37",
              foreground: "#120E0F",
            },
            focus: "#D4AF37",
          },
        },
      },
    }),
  ],
};
