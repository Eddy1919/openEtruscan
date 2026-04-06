"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Box, Row, Stack, Ornament } from "./Layout";

interface SynopticWitness {
  witness: string;
  transcription: string;
  translation: string;
  variants?: number[]; // indices of words that are variants
}

interface AldineSynopticGridProps {
  witnesses: SynopticWitness[];
  className?: string;
}

/**
 * SynopticGrid: A comparative view for multiple textual witnesses.
 * Displays parallel transcriptions and translations.
 */
export function AldineSynopticGrid({ witnesses, className = "" }: AldineSynopticGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Simple rendering for now to fix build. 
  // We'll keep the Stack/Box structure for Alidne aesthetics.

  return (
    <div ref={containerRef} className={`aldine-relative aldine-w-full ${className}`}>
      <div 
        className="aldine-grid aldine-gap-12"
        style={{ gridTemplateColumns: `repeat(${witnesses.length}, 1fr)` }}
      >
        {witnesses.map((w, idx) => (
          <Stack key={idx} gap={8} className="aldine-relative">
             <Box border="bottom" padding={4} className="aldine-mb-6 aldine-border-hairline">
                <Ornament.Label className="aldine-accent aldine-mb-2">{w.witness}</Ornament.Label>
                <h3 className="aldine-text-xl aldine-font-display aldine-font-medium aldine-ink-base aldine-italic">Transcription</h3>
             </Box>
             
             <Stack gap={10}>
                <Box className="aldine-font-editorial aldine-text-lg md:aldine-text-xl aldine-leading-relaxed aldine-ink-base">
                   {w.transcription}
                </Box>
                <Box border="top" padding={4} className="aldine-mt-6 aldine-pt-6 aldine-border-hairline aldine-opacity-60">
                   <Ornament.Label className="aldine-ink-muted aldine-mb-2">Translation</Ornament.Label>
                   <p className="aldine-font-editorial aldine-text-base aldine-italic aldine-ink-base">
                      {w.translation}
                   </p>
                </Box>
             </Stack>
          </Stack>
        ))}
      </div>
    </div>
  );
}
