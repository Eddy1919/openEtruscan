"use client";

import Link from "next/link";
import { Row } from "./Layout";

export function AldineStickyFooter() {
   const year = new Date().getFullYear();

   return (
      <footer className="aldine-border-t aldine-ink-base" style={{ backgroundColor: 'var(--aldine-bone)', padding: '1.25rem 0' }}>
         <div className="aldine-manuscript aldine-flex-col lg:aldine-flex-row aldine-justify-between aldine-items-center aldine-gap-6" style={{ fontSize: '0.75rem' }}>
            
            <div className="aldine-flex-row aldine-items-center aldine-gap-4">
               <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1rem', letterSpacing: '0.1em' }}>𐌏𐌐𐌄𐌍</span>
               <span style={{ opacity: 0.6 }}>Etruscan Initiative &copy; {year}</span>
            </div>

            <nav className="aldine-flex-row aldine-items-center aldine-gap-6 aldine-flex-wrap aldine-justify-center" style={{ letterSpacing: '0.05em' }}>
               <Link href="/docs" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">Documentation</Link>
               <Link href="/explorer" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">Atlas</Link>
               <Link href="/search" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">Corpus</Link>
               <Link href="/names" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">Prosopography</Link>
               <Link href="/timeline" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">Chronology</Link>
               <Link href="https://github.com/openEtruscan" target="_blank" rel="noopener noreferrer" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">GitHub</Link>
               <Link href="https://huggingface.co/openEtruscan" target="_blank" rel="noopener noreferrer" className="aldine-nav-link hover:aldine-accent aldine-transition-colors">HuggingFace</Link>
            </nav>

            <div className="aldine-font-mono" style={{ opacity: 0.5, fontSize: '0.65rem' }}>
               MIT License / CC0 Data
            </div>
         </div>
      </footer>
   );
}
