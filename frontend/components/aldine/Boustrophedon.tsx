"use client";

import React from "react";
import { Box, Stack } from "./Layout";

interface AldineBoustrophedonProps {
  text?: string;
  lines?: string[];
  className?: string;
  startDirection?: "ltr" | "rtl";
}

/**
 * Boustrophedon (Ox-Turning) Flow:
 * Alternates the direction of text line-by-line to mirror ancient 
 * epigraphic standards while maintaining digital legibility.
 * Supports auto-splitting of long text passages.
 */
export function AldineBoustrophedon({ 
  text,
  lines: providedLines, 
  className = "", 
  startDirection = "ltr" 
}: AldineBoustrophedonProps) {
  
  // Calculate lines based on input
  const lines = providedLines || (text ? text.split(/\s+/) : []);

  return (
    <Stack gap={2} className={`aldine-boustrophedon ${className}`}>
      {lines.map((line, i) => {
        const isRtl = startDirection === "ltr" ? i % 2 !== 0 : i % 2 === 0;
        return (
          <Box 
            key={i} 
            className={`aldine-font-editorial aldine-text-lg md:aldine-text-xl aldine-ink-base aldine-leading-snug aldine-transition-all aldine-duration-700 aldine-animate-in aldine-stagger-${Math.min(i + 1, 5)}`}
            style={{ 
              direction: isRtl ? 'rtl' : 'ltr',
              textAlign: isRtl ? 'right' : 'left',
              letterSpacing: "0.05em",
              opacity: 0.8 + (1 / (i + 1)) * 0.2
            }}
          >
            {line}
          </Box>
        );
      })}
      
      <Box className="aldine-mt-4 aldine-opacity-20 aldine-pointer-events-none">
         <span className="aldine-text-[8px] aldine-uppercase aldine-font-bold aldine-tracking-[0.4em] aldine-ink-muted">
            Boustrophedon Flow
         </span>
      </Box>
    </Stack>
  );
}




