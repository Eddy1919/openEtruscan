"use client";

import React from "react";
import { Box } from "./Layout";

interface AldineCodeProps {
  children: string;
  language?: string;
  className?: string;
}

export function AldineCode({ children, language = "etruscan", className = "" }: AldineCodeProps) {
  // Simple "syntax highlighting" for philological diacritics
  const highlight = (text: string) => {
    return text.split(/([θφχśṣχ̇·\[\]\(\)])/).map((part, i) => {
      if (/[θφχśṣχ̇]/.test(part)) {
        return <span key={i} className="aldine-accent aldine-font-bold">{part}</span>;
      }
      if (/[\[\]\(\)]/.test(part)) {
        return <span key={i} className="aldine-ink-muted aldine-opacity-50">{part}</span>;
      }
      if (part === "·") {
        return <span key={i} className="aldine-accent aldine-opacity-80">{part}</span>;
      }
      return part;
    });
  };

  return (
    <Box 
      surface="bone" 
      border="all" 
      padding={6} 
      className={`aldine-font-mono aldine-text-xs aldine-leading-relaxed aldine-overflow-x-auto aldine-rounded-sm ${className}`}
      style={{ backgroundColor: 'rgba(140, 107, 93, 0.05)', borderColor: 'rgba(140, 107, 93, 0.15)' }}
    >
      <pre className="aldine-whitespace-pre-wrap">
        <code>{highlight(children)}</code>
      </pre>
    </Box>
  );
}




