"use client";

import React from "react";
import { Box, Row } from "./Layout";

export function AldineAttribution() {
  return (
    <Box 
      className="aldine-absolute aldine-bottom-6 aldine-left-6 aldine-z-10 aldine-pointer-events-none aldine-animate-in aldine-stagger-4"
    >
      <Row gap={4} align="center" className="aldine-bg-canvas/80 aldine-backdrop-blur-md aldine-px-3 aldine-py-1.5 aldine-rounded-sm aldine-border-all aldine-border-hairline aldine-shadow-sm">
        <span className="aldine-font-epigraphic aldine-accent aldine-text-lg">𐌏𐌐𐌄𐌍</span>
        <div className="aldine-w-line aldine-h-3 aldine-bg-ink-muted/30" />
        <span className="aldine-text-[10px] aldine-font-mono aldine-uppercase aldine-tracking-[0.2em] aldine-ink-muted">Lab Grid Alpha v1.4</span>
        <div className="aldine-w-1 aldine-h-1 aldine-rounded-full aldine-bg-accent aldine-animate-pulse" />
      </Row>
    </Box>
  );
}




