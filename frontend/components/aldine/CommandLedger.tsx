"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Box, Stack, Row } from "./Layout";
import { useAldine } from "./AldineContext";

const ACTIONS = [
  { label: "Search Corpus", shortcut: "S", href: "/search" },
  { label: "Open Spatial Atlas", shortcut: "M", href: "/explorer" },
  { label: "Run Text Normalizer", shortcut: "N", href: "/normalizer" },
  { label: "Restore Lacunae via AI", shortcut: "L", href: "/lacunae" },
  { label: "Corpus Statistics", shortcut: "D", href: "/stats" },
  { label: "Dodecapolis Documentation", shortcut: "A", href: "/docs" },
];

/**
 * CommandLedger: A centralized command palette for quick navigation.
 * Triggered via Cmd+/ or Ctrl+/.
 */
export function AldineCommandLedger() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Trigger on Cmd + / or Ctrl + / or Cmd + K
      if ((e.metaKey || e.ctrlKey) && (e.key === "/" || e.key.toLowerCase() === "k")) {
        e.preventDefault();
        dialogRef.current?.showModal();
      }
    };
    
    const openLedger = () => dialogRef.current?.showModal();

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("aldine-open-ledger", openLedger);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("aldine-open-ledger", openLedger);
    };
  }, []);

  const results = ACTIONS.filter(a => a.label.toLowerCase().includes(query.toLowerCase()));
  const { toggleXmlView, isXmlView } = useAldine();

  const handleSelect = (href: string) => {
    dialogRef.current?.close();
    setQuery("");
    router.push(href);
  };

  const handleToggleXml = () => {
    toggleXmlView();
    dialogRef.current?.close();
    setQuery("");
  };

  return (
    <>
      <dialog 
        ref={dialogRef}
        onClose={() => setQuery("")}
        className="aldine-ledger-dialog"
      >
        <Box surface="canvas" border="all" className="aldine-shadow-lg" style={{ width: '100%', maxWidth: '640px', margin: 'auto', borderRadius: '8px', overflow: 'hidden' }}>
           <Row border="bottom" padding={4} align="center" gap={4} style={{ position: 'relative' }}>
             <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--aldine-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5 }}><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
             <input 
               type="text"
               placeholder="Search historical modules... (Try 'Normalizer')" 
               className="aldine-font-editorial"
               style={{ 
                  flexGrow: 1, backgroundColor: 'transparent', padding: '1rem 0',
                  color: 'var(--aldine-ink)', fontSize: '1.25rem', outline: 'none',
                  border: 'none', fontStyle: 'italic'
               }}
               value={query}
               onChange={e => setQuery(e.target.value)}
               autoFocus
             />
             <button onClick={() => dialogRef.current?.close()} className="aldine-font-mono aldine-uppercase" style={{ fontSize: '10px', backgroundColor: 'var(--aldine-bone)', padding: '2px 6px', border: '1px solid var(--aldine-hairline)' }}>ESC</button>
           </Row>
  
           <Stack as="ul" className="aldine-overflow-y-auto" style={{ maxHeight: '60vh', padding: '1rem', gap: '0.5rem', listStyle: 'none', margin: 0 }}>
             <li>
                <button 
                  onClick={handleToggleXml}
                  className="aldine-transition"
                  style={{ 
                     width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                     padding: '1rem', backgroundColor: 'var(--aldine-bone)', border: '1px dashed var(--aldine-hairline)',
                     borderRadius: '4px', cursor: 'pointer', textAlign: 'left'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--aldine-hairline)'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--aldine-bone)'}
                >
                  <span className="aldine-font-interface" style={{ fontSize: '0.875rem', fontWeight: 600, letterSpacing: '0.05em' }}>{isXmlView ? 'Return to Typeset View' : 'Toggle TEI-XML View'}</span>
                  <span className="aldine-font-mono" style={{ fontSize: '10px', background: 'var(--aldine-canvas)', border: '1px solid var(--aldine-hairline)', padding: '2px 4px' }}>⌘ X</span>
                </button>
             </li>
             {results.length > 0 ? results.map((item, i) => (
               <li key={i}>
                  <button 
                    onClick={() => handleSelect(item.href)}
                    className="aldine-transition"
                    style={{ 
                       width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                       padding: '1rem', backgroundColor: 'transparent',
                       borderRadius: '4px', cursor: 'pointer', textAlign: 'left'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.03)'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <span className="aldine-font-editorial" style={{ fontSize: '1.25rem' }}>{item.label}</span>
                    <span className="aldine-font-mono" style={{ fontSize: '10px', opacity: 0.5 }}>⌘ {item.shortcut}</span>
                  </button>
               </li>
             )) : (
               <li style={{ padding: '2rem', textAlign: 'center', color: 'var(--aldine-ink-muted)', fontStyle: 'italic', fontSize: '0.875rem' }}>No modules match "{query}".</li>
             )}
           </Stack>
        </Box>
      </dialog>
    </>
  );
}




