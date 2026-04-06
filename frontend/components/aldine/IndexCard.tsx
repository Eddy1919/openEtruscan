import React from "react";
import Link from "next/link";
import { AldineEntity } from "./Entity";
import { AldineBoustrophedon } from "./Boustrophedon";

interface KWIC {
  left: string;
  keyword: string;
  right: string;
}

interface AldineIndexCardProps {
  id: string;
  classification?: string | null;
  findspot?: string | null;
  canonical: string;
  kwic?: KWIC;
}

export function AldineIndexCard({ id, classification, findspot, canonical, kwic }: AldineIndexCardProps) {
  return (
    <article 
      className="aldine-bg-canvas aldine-transition-all"
      style={{ 
        padding: 'var(--aldine-space-lg) var(--aldine-space-xl)',
        borderBottom: '1px solid var(--aldine-hairline)',
        position: 'relative'
      }}
    >
      <Link 
        href={`/inscription/${encodeURIComponent(id)}`} 
        className="aldine-w-full aldine-transition gallery-item group" 
        style={{ 
          display: 'flex', 
          flexDirection: 'column', 
          gap: 'var(--aldine-space-sm)'
        }}
      >
        {/* Metadata Header */}
        <header className="aldine-flex-row aldine-font-interface aldine-text-xs" style={{ color: 'var(--aldine-ink-muted)', alignItems: 'center', gap: 'var(--aldine-space-sm)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
           <span className="aldine-font-epigraphic aldine-ink group-hover:aldine-accent aldine-transition-colors" style={{ fontSize: '1rem' }}>{id}</span>
           <span style={{ opacity: 0.3 }}>|</span>
           <AldineEntity type={(classification as any) || "unknown"}>
             {classification || "unknown"}
           </AldineEntity>
           <span style={{ opacity: 0.3 }}>|</span>
           <span className="aldine-italic">{findspot || "Unknown Provenance"}</span>
        </header>
        
        {/* Textual Payload */}
        {kwic ? (
           <div className="aldine-w-full aldine-prose aldine-ink" style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 'var(--aldine-space-md)' }}>
             <div style={{ textAlign: 'right', direction: 'rtl', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--aldine-ink-muted)' }}>
               {kwic.left}
             </div>
             <mark className="aldine-accent aldine-font-epigraphic" style={{ backgroundColor: 'transparent', fontWeight: 600, padding: `0 var(--aldine-space-xs)` }}>
               {kwic.keyword}
             </mark>
             <div style={{ textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--aldine-ink-muted)' }}>
               {kwic.right}
             </div>
           </div>
        ) : (
          <AldineBoustrophedon text={canonical} className="aldine-opacity-90 aldine-text-sm" />
        )}
      </Link>
    </article>
  );
}





