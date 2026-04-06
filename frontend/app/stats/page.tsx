"use client";

import { useEffect, useState } from "react";
import type { StatsSummary } from "@/lib/corpus";
import { fetchStatsSummary, CLASS_COLORS } from "@/lib/corpus";
import { Stack, Row, Box, Ornament } from "@/components/aldine/Layout";
import { AldineManuscript } from "@/components/aldine/Manuscript";

export default function StatsPage() {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStatsSummary()
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Box surface="canvas" className="aldine-w-full aldine-h-full aldine-flex-col aldine-items-center aldine-justify-center" style={{ minHeight: '100vh' }}>
        <p className="aldine-font-mono aldine-uppercase aldine-ink-muted" style={{ fontSize: '0.75rem', letterSpacing: '0.1em', opacity: 0.5 }}>
          Aggregating Corpus Metrics
        </p>
      </Box>
    );
  }

  if (!stats) return null;

  return (
    <Box surface="canvas" className="aldine-w-full aldine-grow aldine-overflow-y-auto" style={{ padding: 'var(--aldine-space-2xl) 0' }}>
      <AldineManuscript align="center">
        
        <Box border="bottom" padding={6} className="aldine-mb-16" style={{ marginBottom: 'var(--aldine-space-3xl)' }}>
          <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '3rem', marginBottom: 'var(--aldine-space-md)' }}>
            Global Statistics
          </h1>
          <p className="aldine-font-editorial aldine-ink-muted aldine-leading-relaxed" style={{ fontSize: '1.25rem', maxWidth: '48rem' }}>
            Real-time analysis of the OpenEtruscan digital record, reflecting geographic coverage, epigraphic diversity, and data completeness.
          </p>
        </Box>

        {/* Hero Stats Array */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--aldine-space-2xl)', marginBottom: 'var(--aldine-space-3xl)' }}>
          {[
            { label: "Aggregate Count", value: (stats?.total ?? 0).toLocaleString(), icon: "𐌏" },
            { label: "Spatial Anchors", value: (stats?.with_coords ?? 0).toLocaleString(), icon: "𐌄" },
            { label: "LOD Intersect", value: (stats?.pleiades_linked ?? 0).toLocaleString(), icon: "𐌈" },
            { label: "Neural Predictions", value: (stats?.classified ?? 0).toLocaleString(), icon: "𐌓" },
          ].map((s) => (
            <Stack key={s.label} border="bottom" padding={4} gap={2} className="aldine-group aldine-relative" style={{ flex: '1 1 200px' }}>
               <span className="aldine-absolute aldine-accent aldine-font-display aldine-italic aldine-transition" style={{ top: '-1.5rem', left: '-1rem', fontSize: '6rem', opacity: 0.05, pointerEvents: 'none', zIndex: 0 }}>{s.icon}</span>
               <Row justify="between" align="end" style={{ width: '100%', zIndex: 1 }}>
                  <span className="aldine-font-interface aldine-uppercase aldine-ink-muted" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.1em' }}>{s.label}</span>
               </Row>
               <span className="aldine-display-title" style={{ fontSize: '3rem', letterSpacing: '-0.02em', zIndex: 1 }}>{s.value}</span>
            </Stack>
          ))}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--aldine-space-3xl)' }}>
          {/* Classification Distribution Grid */}
          <Stack gap={8} style={{ flex: '1 1 400px' }}>
            <Box border="bottom" padding={4}>
               <h2 className="aldine-display-title" style={{ fontSize: '1.5rem', marginBottom: 'var(--aldine-space-xs)' }}>Taxonomic Spread</h2>
               <p className="aldine-font-interface aldine-uppercase aldine-ink-muted" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.1em' }}>Breakdown by Classification</p>
            </Box>
            
            <Stack gap={6}>
              {(stats?.classification_counts || []).map((item) => {
                const cls = (item as any).classification || (item as any)[0] || 'Unknown';
                const count = (item as any).count || (item as any)[1] || 0;
                const pct = stats?.total ? (count / stats.total) * 100 : 0;
                const color = CLASS_COLORS[cls] || CLASS_COLORS.unknown;
                return (
                  <Stack key={cls} gap={1} className="aldine-group">
                    <Row justify="between" align="end" className="aldine-font-interface aldine-uppercase" style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.1em' }}>
                      <span className="aldine-ink-base aldine-transition">{cls}</span>
                      <span className="aldine-font-mono aldine-ink-muted">{count} <span style={{ opacity: 0.4, fontStyle: 'italic', marginLeft: '0.25rem' }}>({pct.toFixed(1)}%)</span></span>
                    </Row>
                    <Box style={{ width: '100%', height: '1px', backgroundColor: 'var(--aldine-bone)', position: 'relative' }}>
                       <div 
                          className="aldine-transition"
                          style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: `${pct}%`, backgroundColor: color, transitionDuration: '1000ms' }}
                       />
                    </Box>
                  </Stack>
                );
              })}
            </Stack>
          </Stack>

          {/* Top Sites Ranking */}
          <Stack gap={8} style={{ flex: '1 1 400px' }}>
            <Box border="bottom" padding={4}>
               <h2 className="aldine-display-title" style={{ fontSize: '1.5rem', marginBottom: 'var(--aldine-space-xs)' }}>Spatial Density</h2>
               <p className="aldine-font-interface aldine-uppercase aldine-ink-muted" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.1em' }}>Leading Geospatial Coordinates</p>
            </Box>
            
            <Stack gap={6}>
              {(stats?.top_sites || []).map((item, i) => {
                const site = (item as any).findspot || (item as any)[0] || 'Unknown';
                const count = (item as any).count || (item as any)[1] || 0;
                const pct = stats?.total ? (count / stats.total) * 100 : 0;
                return (
                  <Row key={site} gap={4} className="aldine-group">
                    <Box className="aldine-font-mono aldine-ink-muted" style={{ width: '1.5rem', fontSize: '0.75rem', opacity: 0.4 }}>0{i+1}</Box>
                    <Stack gap={1} style={{ flexGrow: 1 }}>
                       <Row justify="between" align="end">
                          <span className="aldine-font-editorial aldine-ink-base aldine-transition" style={{ fontSize: '0.875rem', fontWeight: 600 }}>{site}</span>
                          <span className="aldine-font-mono aldine-ink-muted" style={{ fontSize: '0.75rem' }}>{count}</span>
                       </Row>
                       <Box border="bottom" style={{ width: '100%', height: '1px', borderStyle: 'dashed', borderColor: 'var(--aldine-ink)', opacity: 0.2, position: 'relative' }}>
                          <div className="aldine-transition" style={{ height: '100%', backgroundColor: 'var(--aldine-accent)', width: `${pct * 3}%`, transitionDuration: '1000ms' }} />
                       </Box>
                    </Stack>
                  </Row>
                );
              })}
            </Stack>
          </Stack>
        </div>

      </AldineManuscript>
    </Box>
  );
}
