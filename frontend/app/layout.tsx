import type { Metadata } from "next";
import { Inter, DM_Serif_Display, JetBrains_Mono } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { Analytics } from "@vercel/analytics/next";
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
  title: "OpenEtruscan | Digital Corpus Platform",
  description:
    "Open-source tools for Etruscan epigraphy: normalize ancient texts, explore 4,700+ inscriptions on an interactive map, and classify inscriptions with neural networks.",
  metadataBase: new URL('https://openetruscan.com'),
  keywords: [
    "Etruscan", "epigraphy", "corpus", "archaeology", "ancient history",
    "digital humanities", "NLP", "old italic", "Tuscan", "inscriptions"
  ],
  authors: [{ name: "OpenEtruscan Contributors" }],
  openGraph: {
    title: "OpenEtruscan | Digital Corpus Platform",
    description: "Open-source digital corpus and computational toolkit for the study of Etruscan epigraphy.",
    url: "https://openetruscan.com",
    siteName: "OpenEtruscan",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "OpenEtruscan | Digital Corpus",
    description: "Open-source digital corpus and computational toolkit for the study of Etruscan epigraphy.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
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
        <Analytics />
      </body>
    </html>
  );
}
