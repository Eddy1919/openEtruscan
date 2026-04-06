"use client";

import { useState, useMemo, useEffect, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import type { TimelineItem } from "@/lib/corpus";
import { Marker, Popup } from "react-map-gl/mapbox";
import { AldineMap } from "@/components/aldine/Map";
import { AldineChronosRange } from "@/components/aldine/ChronosRange";
import { Row, Box, Stack, Ornament } from "@/components/aldine/Layout";
import { AldineSplitPane } from "@/components/aldine/SplitPane";

const PERIODS = [
  { label: "Pre-700 BCE", min: -1000, max: -700, color: "#A2574B" },
  { label: "700-500 BCE", min: -700, max: -500, color: "#8E706A" },
  { label: "500-300 BCE", min: -500, max: -300, color: "#544641" },
  { label: "300-100 BCE", min: -300, max: -100, color: "#8c6b5d" },
  { label: "Post-100 BCE", min: -100, max: 500, color: "#2B211E" },
];

function getPeriodColor(dateApprox: number): string {
  for (const p of PERIODS) {
    if (dateApprox >= p.min && dateApprox < p.max) return p.color;
  }
  return "#6b6962";
}

interface ClientTimelineProps {
  initialItems: TimelineItem[];
}

function TimelineContent({ initialItems }: ClientTimelineProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [range, setRange] = useState<[number, number]>(() => {
    const minParam = searchParams.get("min");
    const maxParam = searchParams.get("max");
    return [
      minParam ? Number(minParam) : -800,
      maxParam ? Number(maxParam) : -100
    ];
  });
  
  const [hoverInfo, setHoverInfo] = useState<any>(null);

  // Sync URL State
  useEffect(() => {
    const params = new URLSearchParams();
    params.set("min", range[0].toString());
    params.set("max", range[1].toString());
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [range, pathname, router]);

  const filtered = useMemo(() => {
    return initialItems.filter(
      (i) => i.date_approx >= range[0] && i.date_approx <= range[1]
    );
  }, [initialItems, range]);

  const distribution = useMemo(() => {
    const bins = 40;
    const dist = new Array(bins).fill(0);
    initialItems.forEach(i => {
      const idx = Math.floor(((i.date_approx - (-1000)) / (200 - (-1000))) * bins);
      if (idx >= 0 && idx < bins) dist[idx]++;
    });
    return dist;
  }, [initialItems]);

  const clusters = useMemo(() => {
    const map = new Map<string, { lat: number; lon: number; name: string; count: number; items: TimelineItem[] }>();
    filtered.forEach((i) => {
      const key = `${i.findspot_lat.toFixed(2)}_${i.findspot_lon.toFixed(2)}`;
      if (!map.has(key)) {
        map.set(key, { lat: i.findspot_lat, lon: i.findspot_lon, name: i.findspot || "Unknown", count: 0, items: [] });
      }
      const cluster = map.get(key)!;
      cluster.count++;
      cluster.items.push(i);
    });
    return Array.from(map.values());
  }, [filtered]);

  const periodCounts = useMemo(() => {
    return PERIODS.map((p) => ({
      ...p,
      count: filtered.filter(
        (i) => i.date_approx >= p.min && i.date_approx < p.max
      ).length,
    }));
  }, [filtered]);

  const ControlPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-y-auto aldine-px-8 aldine-py-16 aldine-bg-canvas">
        <Box className="aldine-mb-16 aldine-animate-in aldine-stagger-1">
           <Ornament.Label className="aldine-accent">Temporal Distribution</Ornament.Label>
           <h1 className="aldine-text-4xl md:aldine-text-5xl aldine-font-display aldine-font-medium aldine-ink-base aldine-italic aldine-mb-6">
             Etruscan Chronology
           </h1>
           <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed aldine-opacity-70">
             Spatiotemporal analysis of dated inscriptions from the 8th Century BCE onward.
           </p>
        </Box>

        <Stack gap={12} className="aldine-animate-in aldine-stagger-2">
           <AldineChronosRange 
              min={-1000}
              max={200}
              value={range}
              onChange={setRange}
              distribution={distribution}
              uncertainty={25}
           />

           <Stack gap={4}>
              <Box border="bottom" padding={2} className="aldine-border-hairline aldine-mb-6">
                 <Ornament.Label className="aldine-accent">Period Density</Ornament.Label>
              </Box>
              <Stack gap={6}>
                 {periodCounts.map((p, i) => {
                   const pct = initialItems.length ? (p.count / initialItems.length) * 100 : 0;
                   return (
                     <Stack key={p.label} gap={2} className={`aldine-group aldine-animate-in aldine-stagger-${Math.min(i + 1, 5)}`}>
                       <Row justify="between">
                          <Row gap={3} align="center">
                             <div className="aldine-w-2 aldine-h-2 aldine-rounded-full" style={{ backgroundColor: p.color }} />
                             <span className="aldine-label aldine-text-[10px] group-hover:aldine-ink-base aldine-transition-colors">{p.label}</span>
                          </Row>
                          <span className="aldine-text-xs aldine-font-mono aldine-font-bold aldine-ink-base">{p.count}</span>
                       </Row>
                       <Box className="aldine-w-full aldine-h-line aldine-bg-bone/40 aldine-relative aldine-overflow-hidden">
                          <div className="aldine-absolute aldine-top-0 aldine-left-0 aldine-h-full aldine-transition-all aldine-duration-700" style={{ width: `${pct}%`, backgroundColor: p.color, opacity: 0.8 }} />
                       </Box>
                     </Stack>
                   );
                 })}
              </Stack>
           </Stack>

           <Box border="all" padding={6} className="aldine-bg-bone/20 aldine-border-bone aldine-mt-auto aldine-animate-in aldine-stagger-3">
              <Stack gap={2}>
                 <Ornament.Label className="aldine-opacity-40">Aggregate Records</Ornament.Label>
                 <span className="aldine-text-3xl aldine-font-display aldine-font-bold aldine-accent">{filtered.length.toLocaleString()}</span>
                 <p className="aldine-text-[9px] aldine-font-interface aldine-ink-muted aldine-uppercase aldine-tracking-[0.2em] aldine-opacity-60">Dated and Cataloged</p>
              </Stack>
           </Box>
        </Stack>
     </Box>
  );

  const MapPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-hidden aldine-relative aldine-bg-bone">
        <AldineMap
          initialViewState={{ longitude: 12.0, latitude: 42.8, zoom: 6 }}
          onClick={() => setHoverInfo(null)}
        >
          {clusters.map((c, i) => {
             const markerColor = c.items[0]?.date_approx != null ? getPeriodColor(c.items[0].date_approx) : "#8c6b5d";
             const radiusScale = Math.min(1 + Math.sqrt(c.count) * 0.15, 2.5);
             return (
               <Marker 
                 key={i} 
                 longitude={c.lon} 
                 latitude={c.lat}
                 onClick={e => {
                   e.originalEvent.stopPropagation();
                   // @ts-ignore
                   setHoverInfo({ ...c, color: markerColor });
                 }}
               >
                 <div style={{ position: 'relative', cursor: 'pointer', transform: `translate(-50%, -50%) scale(${radiusScale})`, transition: 'all 0.3s ease' }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.5))' }}>
                      <path d="M12 2L2 12L12 22L22 12L12 2Z" fill={"var(--aldine-canvas)"} stroke={markerColor} strokeWidth="1.5"/>
                      <circle cx="12" cy="12" r="3" fill={markerColor}/>
                    </svg>
                 </div>
               </Marker>
             );
          })}

          {hoverInfo && (
             <Popup
               // @ts-ignore
               longitude={hoverInfo.lon}
               // @ts-ignore
               latitude={hoverInfo.lat}
               offset={[0, -10]}
               closeButton={false}
               closeOnClick={false}
               anchor="bottom"
             >
               <article className="aldine-card aldine-p-4" style={{ minWidth: '150px' }}>
                  <span className="aldine-font-epigraphic" style={{ fontSize: '0.75rem', display: 'block', marginBottom: '0.25rem', color: (hoverInfo as any).color }}>
                    {(hoverInfo as any).name || "Unknown Site"}
                  </span>
                  <p className="aldine-font-editorial aldine-font-bold" style={{ fontSize: '0.875rem' }}>
                    {(hoverInfo as any).count} Inscriptions
                  </p>
               </article>
             </Popup>
          )}

          <div className="aldine-absolute aldine-bottom-8 aldine-right-8 aldine-pointer-events-none aldine-opacity-30">
             <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-[0.3em] aldine-accent aldine-font-mono">OpenEtruscan Lab Grid v1.0</span>
          </div>
        </AldineMap>
     </Box>
  );

  return (
    <Box className="aldine-grow aldine-flex aldine-flex-col" style={{ minHeight: "calc(100vh - 84px)" }}>
       <AldineSplitPane leftPane={ControlPane} rightPane={MapPane} />
    </Box>
  );
}

export function ClientTimelineMap(props: ClientTimelineProps) {
  return (
    <Suspense fallback={
       <div className="aldine-w-full aldine-canvas aldine-flex-col aldine-items-center aldine-justify-center" style={{ minHeight: '60vh' }}>
          <Ornament.Label className="aldine-animate-pulse">Loading Chronology Matrix</Ornament.Label>
       </div>
    }>
       <TimelineContent {...props} />
    </Suspense>
  );
}
