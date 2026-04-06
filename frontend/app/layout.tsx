import type { Metadata } from "next";
import { Inter, Cormorant_Garamond, JetBrains_Mono } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { Analytics } from "@vercel/analytics/next";
import { AldineNav } from "@/components/aldine/Nav";
import { AldineStickyFooter } from "@/components/aldine/StickyFooter";
import { AldineSelectionEruption } from "@/components/aldine/SelectionEruption";
import { AldineCommandLedger } from "@/components/aldine/CommandLedger";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const cormorant = Cormorant_Garamond({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--aldine-font-display",
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

import { AldineProvider } from "@/components/aldine/AldineContext";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${cormorant.variable} ${jetbrains.variable}`}
    >
      <head>
        <link rel="stylesheet" href="/cdn/aldine.min.css" />
      </head>
      <body className="aldine-screen aldine-flex aldine-flex-col aldine-bg-canvas aldine-ink-base aldine-antialiased">
        <AldineProvider>
          <AldineNav />
          <main className="aldine-grow aldine-flex aldine-flex-col">
            {children}
          </main>
          <AldineStickyFooter />
          <AldineCommandLedger />
        </AldineProvider>
        <SpeedInsights />
        <Analytics />
      </body>
    </html>
  );
}





