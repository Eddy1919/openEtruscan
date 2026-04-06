"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Box } from "./Layout";

const SECTIONS = [
  {
    title: "Archive",
    links: [
      { href: "/search", label: "Search Corpus" },
      { href: "/explorer", label: "Spatial Atlas" },
      { href: "/timeline", label: "Chronology" },
      { href: "/concordance", label: "Concordance" },
    ]
  },
  {
    title: "Archaeometry",
    links: [
      { href: "/classifier", label: "Neural Classifier" },
      { href: "/normalizer", label: "Text Normalizer" },
      { href: "/lacunae", label: "Restore Lacunae" },
      { href: "/names", label: "Prosopography" },
      { href: "/compare", label: "Synoptic Comparison" },
    ]
  },
  {
    title: "Documentation",
    links: [
      { href: "/stats", label: "Corpus Statistics" },
      { href: "/docs", label: "System API" },
    ]
  }
];

export function AldineNav() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);

  // Close menus on route change
  useEffect(() => {
    setIsOpen(false);
    setActiveDropdown(null);
  }, [pathname]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setActiveDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <nav 
      aria-label="Primary" 
      ref={navRef}
      className="aldine-w-full aldine-py-4 aldine-px-6 aldine-flex-row aldine-justify-between aldine-items-center aldine-border-b"
      style={{ backgroundColor: 'var(--aldine-canvas)', zIndex: 50, position: 'relative' }}
    >
      {/* Brand */}
      <Link href="/" className="aldine-flex-row aldine-gap-2 aldine-items-center aldine-hover-expand" onClick={() => setActiveDropdown(null)}>
        <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1.5rem' }}>𐌏𐌐𐌄𐌍</span>
        <span className="aldine-ink-base" style={{ fontStyle: 'italic', fontWeight: 300, fontSize: '1.25rem' }}>Etruscan</span>
      </Link>

      {/* Desktop Links (Multi-Section Dropdowns) */}
      <div className="aldine-hidden lg:aldine-flex aldine-flex-row aldine-gap-8 aldine-items-center">
        {SECTIONS.map((section) => (
          <div key={section.title} className="aldine-relative">
            <button 
              className="aldine-nav-link aldine-flex-row aldine-items-center aldine-gap-1 aldine-transition-colors"
              style={{ color: activeDropdown === section.title ? 'var(--aldine-accent)' : 'inherit' }}
              onClick={() => setActiveDropdown(activeDropdown === section.title ? null : section.title)}
            >
              <span className="aldine-relative">
                 {section.title}
                 {activeDropdown === section.title && (
                   <span className="aldine-absolute aldine-bottom-0 aldine-left-0 aldine-w-full" style={{ height: '1px', backgroundColor: 'var(--aldine-accent)', transform: 'translateY(2px)' }} />
                 )}
              </span>
              <svg width="8" height="5" viewBox="0 0 10 6" fill="none" style={{ transform: activeDropdown === section.title ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', opacity: activeDropdown === section.title ? 1 : 0.5 }}>
                <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            
            {activeDropdown === section.title && (
              <Box 
                surface="bone"
                border="all"
                className="aldine-absolute aldine-shadow-lg aldine-animate-scale"
                style={{ 
                  top: 'calc(100% + 8px)', 
                  left: '50%',
                  transform: 'translateX(-50%)',
                  minWidth: '220px', 
                  zIndex: 1000, 
                  padding: '6px',
                  backdropFilter: 'blur(12px)',
                  backgroundColor: 'rgba(250, 250, 249, 0.95)'
                }}
              >
                {section.links.map((link, i) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`aldine-w-full aldine-nav-link aldine-flex-row aldine-items-center aldine-transition-colors aldine-animate-in aldine-stagger-${Math.min(i + 1, 5)}`}
                    style={{ 
                      textTransform: 'none', 
                      padding: '10px 14px',
                      color: pathname === link.href ? 'var(--aldine-accent)' : 'var(--aldine-ink)',
                      borderRadius: '4px',
                      fontSize: '0.9rem',
                      fontFamily: 'var(--aldine-font-interface)'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--aldine-glass)'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    {link.label}
                  </Link>
                ))}
              </Box>
            )}
          </div>
        ))}
        <Link 
          href="/manifesto" 
          className="aldine-nav-link aldine-flex-row aldine-items-center aldine-ml-4 aldine-border-l aldine-pl-8 aldine-border-bone"
          style={{ 
            fontWeight: pathname === "/manifesto" ? 600 : 400,
            color: pathname === "/manifesto" ? 'var(--aldine-accent)' : 'var(--aldine-ink-base)'
          }}
        >
          Manifesto
        </Link>
        <button
          onClick={() => window.dispatchEvent(new Event("aldine-open-ledger"))}
          className="aldine-nav-link aldine-flex-row aldine-items-center aldine-ml-4 aldine-border-l aldine-pl-8 aldine-border-bone"
          style={{ fontWeight: 400, color: 'var(--aldine-ink-muted)' }}
        >
          Command ⌘K
        </button>
      </div>

      {/* Universal Menu Trigger */}
      <div className="lg:aldine-hidden">
        <button 
          className="aldine-nav-link" 
          onClick={() => setIsOpen(true)}
        >
          Menu
        </button>
      </div>

      {/* Mobile Menu Overlay */}
      {isOpen && (
        <div 
          className="aldine-fixed aldine-inset-0 aldine-flex aldine-flex-col aldine-overflow-y-auto aldine-z-overlay aldine-animate-in aldine-animate-scale" 
          style={{ 
            backgroundColor: 'var(--aldine-canvas)',
            padding: '2rem',
          }}
        >
          {/* Glass background factor */}
          <div className="aldine-absolute aldine-inset-0 aldine-glass aldine-opacity-10 aldine-pointer-events-none" />

          {/* Dialog Header */}
          <header className="aldine-flex aldine-flex-row aldine-justify-between aldine-items-center aldine-mb-16 aldine-relative aldine-z-10">
            <Link href="/" className="aldine-flex aldine-flex-row aldine-gap-2 aldine-items-center aldine-animate-in aldine-stagger-1" onClick={() => setIsOpen(false)}>
              <span className="aldine-font-epigraphic aldine-accent aldine-text-2xl">𐌏𐌐𐌄𐌍</span>
              <span className="aldine-ink-base aldine-italic aldine-font-light aldine-text-xl">Etruscan</span>
            </Link>
            <button 
              className="aldine-nav-link aldine-animate-in aldine-stagger-1"
              onClick={() => setIsOpen(false)}
            >
              Close
            </button>
          </header>

          {/* Categorized Mobile Links */}
          <div className="aldine-flex aldine-flex-col aldine-gap-12 aldine-mt-4 aldine-relative aldine-z-10">
            {SECTIONS.map((section, idx) => (
              <div key={section.title} className={`aldine-flex aldine-flex-col aldine-gap-6 aldine-animate-in aldine-stagger-${Math.min(idx + 2, 5)}`}>
                <span className="aldine-ink-muted aldine-font-interface aldine-text-[10px] aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-opacity-60 aldine-border-b aldine-border-bone aldine-pb-2">
                  {section.title}
                </span>
                <div className="aldine-flex aldine-flex-col aldine-gap-6 aldine-pl-4 aldine-border-l aldine-border-bone">
                  {section.links.map((link, j) => (
                    <Link 
                      key={link.href} 
                      href={link.href} 
                      onClick={() => setIsOpen(false)}
                      className={`aldine-display-title aldine-transition-colors aldine-hover-accent aldine-animate-in aldine-stagger-${Math.min(j + 3, 5)}`}
                      style={{ 
                         fontSize: '2rem',
                         color: pathname === link.href ? 'var(--aldine-accent)' : 'var(--aldine-ink-base)',
                         fontWeight: pathname === link.href ? 500 : 300,
                         fontStyle: 'italic'
                      }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
            
            <div className="aldine-flex aldine-flex-col aldine-gap-6 aldine-animate-in aldine-stagger-5">
              <span className="aldine-ink-muted aldine-font-interface aldine-text-[10px] aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-opacity-60 aldine-border-b aldine-border-bone aldine-pb-2">
                Mission
              </span>
              <div className="aldine-flex aldine-flex-col aldine-gap-6 aldine-pl-4 aldine-border-l aldine-border-bone">
                <Link 
                  href="/manifesto" 
                  onClick={() => setIsOpen(false)}
                  className="aldine-display-title aldine-italic aldine-font-light aldine-hover-accent aldine-transition-colors"
                  style={{ fontSize: '2rem', color: pathname === "/manifesto" ? 'var(--aldine-accent)' : 'var(--aldine-ink-base)' }}
                >
                  Manifesto
                </Link>
                <button 
                  onClick={() => { setIsOpen(false); window.dispatchEvent(new Event("aldine-open-ledger")); }}
                  className="aldine-display-title aldine-italic aldine-font-light aldine-hover-accent aldine-transition-colors aldine-text-left"
                  style={{ fontSize: '2rem', color: 'var(--aldine-ink-base)' }}
                >
                  Command ⌘K
                </button>
              </div>
            </div>
          </div>

          {/* Abstract background glyph */}
          <div className="aldine-absolute aldine-bottom-0 aldine-right-0 aldine-p-12 aldine-opacity-5 aldine-pointer-events-none">
             <span className="aldine-font-epigraphic aldine-text-[12rem]">𐌀𐌅𐌉𐌋</span>
          </div>
        </div>
      )}
    </nav>
  );
}

