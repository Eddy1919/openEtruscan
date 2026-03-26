import type { Metadata } from "next";
import { Inter, DM_Serif_Display, JetBrains_Mono } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const dmSerif = DM_Serif_Display({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-dm-serif",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "OpenEtruscan — Digital Corpus Platform",
  description:
    "Open-source tools for Etruscan epigraphy: normalize ancient texts, explore 4,700+ inscriptions on an interactive map, and classify inscriptions with neural networks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${dmSerif.variable} ${jetbrains.variable}`}
    >
      <body>
        <Nav />
        {children}
        <Footer />
        <SpeedInsights />
      </body>
    </html>
  );
}
