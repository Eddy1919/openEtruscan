"use client";

import React from "react";
import { Box, Stack, Ornament } from "@/components/aldine/Layout";
import { AldineSplitPane } from "@/components/aldine/SplitPane";
import { AldineSynopticGrid } from "@/components/aldine/SynopticGrid";
import { AldineCitationBlock } from "@/components/aldine/CitationBlock";

const COMPARISON_DATA = [
  {
    witness: "CIE 1.1",
    transcription: "mi larice śatnaie",
    translation: "I am [the vessel] of Laris Satnaie",
    variants: [0, 1, 2]
  },
  {
    witness: "REE 2024",
    transcription: "mi lariś śatnaieś",
    translation: "I [belong to] Laris Satnaie",
    variants: [0, 1, 3]
  },
  {
    witness: "TLE 14",
    transcription: "mi lariś śatnas",
    translation: "I [am] Laris Satna",
    variants: [0, 1, 4]
  }
];

export default function ComparisonPage() {
  const ControlPane = (
     <Stack gap={12} className="aldine-canvas aldine-w-full aldine-h-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <Stack gap={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Philological Apparatus</Ornament.Label>
           <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '2.25rem' }}>
             Synoptic Comparison
           </h1>
           <p className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.125rem', opacity: 0.7 }}>
             Semantic alignment of textual witnesses across the major corpora (CIE, TLE, REE).
             Visualizing morphosyntactic variation and scribal idiosyncrasies.
           </p>
        </Stack>

        <Box border="all" padding={6} surface="bone" className="aldine-animate-in aldine-stagger-3" style={{ opacity: 0.8, borderStyle: 'dashed' }}>
           <Stack gap={4}>
              <Ornament.Label className="aldine-ink-muted">Instructional Note</Ornament.Label>
              <p className="aldine-font-editorial aldine-ink-base" style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
                Connective ribbons represent shared semantic roots. Hover over transcription fragments 
                to highlight localized variants across the synoptic vertical.
              </p>
           </Stack>
        </Box>
     </Stack>
  );

  const AnalysisPane = (
     <Stack gap={12} surface="bone" className="aldine-h-full aldine-w-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <Stack gap={4} border="bottom" padding={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-xl)' }}>
           <Ornament.Label className="aldine-accent">Synoptic Matrix</Ornament.Label>
        </Stack>

        <Box className="aldine-animate-in aldine-stagger-2">
           <Box surface="canvas" border="all" padding={6} style={{ boxShadow: 'var(--aldine-shadow-sm)' }}>
               <AldineSynopticGrid witnesses={COMPARISON_DATA} />
           </Box>
        </Box>

        <Box style={{ marginTop: 'auto', paddingTop: 'var(--aldine-space-2xl)' }}>
            <AldineCitationBlock id="SYNOPTIC-SATNAIE-001" title="Synoptic Analysis of Satnaie Witnesses" />
        </Box>
     </Stack>
  );

  return (
     <Box className="aldine-grow aldine-flex aldine-col" style={{ minHeight: 'calc(100vh - 84px)' }}>
        <AldineSplitPane leftPane={ControlPane} rightPane={AnalysisPane} initialRatio={0.35} />
     </Box>
  );
}
