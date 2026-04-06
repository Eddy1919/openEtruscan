"use client";

import { useState, useMemo } from "react";
import { Marker, Popup } from "react-map-gl/mapbox";
import { AldineMap } from "@/components/aldine/Map";
import { AldineIndexCard } from "@/components/aldine/IndexCard";
import { AldineSelect } from "@/components/aldine/Select";
import type { Inscription, StatsSummary } from "@/lib/corpus";

interface ExplorerProps {
  initialInscriptions?: Inscription[];
  stats?: StatsSummary;
}

export function ClientExplorerMap({ initialInscriptions = [], stats }: ExplorerProps) {
  const [inscriptions] = useState<Inscription[]>(initialInscriptions);
  const [selected, setSelected] = useState<Inscription | null>(null);
  
  const [filterSite, setFilterSite] = useState("");
  const [filterClass, setFilterClass] = useState("");

  const filteredInscriptions = useMemo(() => {
    return inscriptions.filter(i => {
      const matchSite = !filterSite || i.findspot === filterSite;
      const matchClass = !filterClass || i.classification === filterClass;
      return matchSite && matchClass;
    });
  }, [inscriptions, filterSite, filterClass]);

  // aldine.entity logic for typographic markers
  const renderMarker = (i: Inscription) => {
    const isSelected = selected?.id === i.id;
    return (
      <Marker
        key={i.id}
        longitude={i.findspot_lon || 0}
        latitude={i.findspot_lat || 0}
        onClick={e => {
          e.originalEvent.stopPropagation();
          setSelected(i);
        }}
      >
         <div style={{ position: 'relative', cursor: 'pointer', transform: `translate(-50%, -50%) ${isSelected ? 'scale(1.2)' : 'scale(1)'}`, transition: 'all 0.3s ease' }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style={{ filter: isSelected ? 'drop-shadow(0 0 8px var(--aldine-accent))' : 'drop-shadow(0 1px 2px rgba(0,0,0,0.5))' }}>
              <path d="M12 2L2 12L12 22L22 12L12 2Z" fill={isSelected ? "var(--aldine-accent)" : "var(--aldine-canvas)"} stroke={isSelected ? "var(--aldine-canvas)" : "var(--aldine-ink-muted)"} strokeWidth="1.5"/>
              <circle cx="12" cy="12" r="3" fill={isSelected ? "var(--aldine-canvas)" : "var(--aldine-accent)"}/>
            </svg>
            {isSelected && (
              <span className="aldine-font-mono aldine-uppercase" style={{ position: 'absolute', left: '100%', top: '50%', transform: 'translateY(-50%)', marginLeft: '8px', fontSize: '10px', background: 'var(--aldine-bone)', padding: '2px 6px', border: '1px solid var(--aldine-ink)', whiteSpace: 'nowrap', zIndex: 50 }}>
                 {i.findspot || i.id}
              </span>
            )}
         </div>
      </Marker>
    );
  };

  return (
    <main className="aldine-relative aldine-w-full" style={{ height: 'calc(100vh - var(--aldine-nav-height, 5rem))', display: 'flex', overflow: 'hidden' }}>
      
      {/* The Epistemological Index Overlay (Left Gutter equivalent) */}
      <aside className="aldine-absolute aldine-inset-0 aldine-bg-bone aldine-border-r" style={{ width: '400px', zIndex: 10, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--aldine-bone)' }}>
          <header className="aldine-p-6 aldine-border-b">
             <h2 className="aldine-display-title" style={{ fontSize: '1.5rem', fontStyle: 'italic' }}>Spatial Atlas</h2>
             <p className="aldine-prose" style={{ fontSize: '0.875rem', color: 'var(--aldine-ink-muted)', marginTop: '1rem' }}>
                Topographical distribution of the Etruscan corpus. Filter by provenance or epigraphic classification.
             </p>
          </header>

          <div className="aldine-p-6 aldine-flex-col aldine-gap-6 aldine-border-b">
             <AldineSelect
                label="Provenance"
                options={[
                  { label: "All Sites", value: "" },
                  ...(stats?.distinct_sites || []).map((s: string) => ({ label: s, value: s }))
                ]}
                value={filterSite}
                onChange={setFilterSite}
             />

             <AldineSelect
                label="Classification"
                options={[
                  { label: "All Classifications", value: "" },
                  ...(stats?.distinct_classifications || []).map((c: string) => ({ label: c, value: c }))
                ]}
                value={filterClass}
                onChange={setFilterClass}
             />
          </div>

          <div className="aldine-flex-col aldine-grow" style={{ overflowY: 'auto', padding: '1.5rem' }}>
             <label className="aldine-font-epigraphic aldine-mb-4" style={{ fontSize: '0.75rem', opacity: 0.6 }}>Results Matrix ({filteredInscriptions.length})</label>
             <div className="aldine-flex-col aldine-gap-4">
               {filteredInscriptions.slice(0, 50).map(i => (
                 <div 
                   key={i.id} 
                   className="aldine-transition"
                   style={{ 
                     opacity: selected?.id === i.id ? 1 : 0.6,
                     cursor: 'pointer'
                   }}
                   onClick={() => setSelected(i)}
                 >
                    <AldineIndexCard {...i} />
                 </div>
               ))}
             </div>
          </div>
      </aside>

      {/* Mapbox Canvas Bleeding */}
      <section className="aldine-relative aldine-grow" style={{ marginLeft: '400px', height: '100%' }}>
        <AldineMap
          initialViewState={{
            longitude: 11.5,
            latitude: 42.5,
            zoom: 6.5
          }}
          onClick={() => setSelected(null)}
        >
          {filteredInscriptions.slice(0, 200).map(renderMarker)}

          {selected && selected.findspot_lon && selected.findspot_lat && (
             <Popup
               longitude={selected.findspot_lon}
               latitude={selected.findspot_lat}
               offset={[0, -10]}
               closeButton={false}
               closeOnClick={false}
               anchor="bottom"
             >
               <article className="aldine-card aldine-p-6" style={{ minWidth: '200px' }}>
                  <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '0.75rem', display: 'block', marginBottom: '0.5rem' }}>
                    {selected.id}
                  </span>
                  <p className="aldine-prose" style={{ fontSize: '0.875rem', fontStyle: 'italic' }}>
                    {selected.canonical}
                  </p>
               </article>
             </Popup>
          )}
        </AldineMap>
      </section>

    </main>
  );
}
