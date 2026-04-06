"use client";

import React from "react";
import { Box, Row, Stack } from "./Layout";
import { AldinePaleographyLens } from "./PaleographyLens";

interface AldineTableProps {
  headers: React.ReactNode[];
  children: React.ReactNode;
  stickyHeader?: boolean;
  className?: string;
}

export function AldineTable({ headers, children, stickyHeader = true, className = "" }: AldineTableProps) {
  return (
    <Box className={`aldine-w-full aldine-relative ${className}`} role="table">
      {/* Header Row */}
      <div 
        role="row" 
        className={`aldine-grid aldine-grid-cols-4 aldine-gap-6 aldine-text-[10px] aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-ink-muted aldine-pb-4 aldine-border-b aldine-border-ink-muted-alpha ${stickyHeader ? 'aldine-sticky aldine-top-0 aldine-z-20 aldine-bg-canvas' : ''}`}
        style={{ gridTemplateColumns: 'minmax(120px, 1fr) 2fr 1.5fr 2fr' }}
      >
        {headers.map((h, i) => (
          <div key={i} role="columnheader" className={`${i === 1 ? 'aldine-text-right' : i === 2 ? 'aldine-text-center aldine-accent' : 'aldine-text-left'}`}>
            {h}
          </div>
        ))}
      </div>

      {/* Body */}
      <Stack className="aldine-flex aldine-flex-col">
        {children}
      </Stack>
    </Box>
  );
}

interface AldineTableRowProps {
  id: string;
  left: string;
  keyword: string;
  right: string;
  href?: string;
  onClick?: () => void;
  className?: string;
}

export function AldineKWICRow({ id, left, keyword, right, href, onClick, className = "" }: AldineTableRowProps) {
  const Content = (
    <div 
      role="row" 
      className={`aldine-grid aldine-grid-cols-4 aldine-gap-6 aldine-py-4 aldine-border-b aldine-border-bone aldine-group hover:aldine-bg-bone/40 aldine-transition-colors aldine-items-center aldine-font-editorial aldine-text-lg aldine-ink-base ${className}`}
      style={{ gridTemplateColumns: 'minmax(120px, 1fr) 2fr 1.5fr 2fr' }}
    >
      <div role="cell" className="aldine-font-interface aldine-text-xs aldine-font-bold aldine-ink-muted group-hover:aldine-ink-base aldine-transition-colors aldine-truncate aldine-pr-4">
        {id}
      </div>
      <div role="cell" className="aldine-text-right aldine-truncate aldine-opacity-70 aldine-font-light aldine-italic" dir="rtl">
        {left}
      </div>
      <div role="cell" className="aldine-text-center aldine-font-bold aldine-accent aldine-px-4 aldine-tracking-tight aldine-relative">
        <AldinePaleographyLens scale={1.2} blur="1px" className="aldine-rounded-sm">
          <span className="aldine-bg-accent/5 aldine-px-2 aldine-py-1 aldine-rounded-sm aldine-inline-block">{keyword}</span>
        </AldinePaleographyLens>
      </div>
      <div role="cell" className="aldine-text-left aldine-truncate aldine-opacity-70 aldine-font-light aldine-italic">
        {right}
      </div>
    </div>
  );

  if (href) {
    return (
      <a href={href} className="aldine-block aldine-no-underline">
        {Content}
      </a>
    );
  }

  return (
    <div onClick={onClick} className={onClick ? 'aldine-cursor-pointer' : ''}>
      {Content}
    </div>
  );
}




