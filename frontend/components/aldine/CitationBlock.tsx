"use client";

import { useState } from "react";
import { Box, Row, Stack, Ornament } from "./Layout";

interface AldineCitationBlockProps {
  id: string;
  title: string;
  author?: string;
  year?: number | string;
  url?: string;
  publisher?: string;
  className?: string;
}

export function AldineCitationBlock({
  id,
  title,
  author = "OpenEtruscan Digital Corpus",
  year = new Date().getFullYear(),
  url = typeof window !== "undefined" ? window.location.href : "",
  publisher = "OpenEtruscan Project",
  className = ""
}: AldineCitationBlockProps) {
  const [copied, setCopied] = useState(false);

  const citations = {
    chicago: `${author}. "${title}." ${publisher}, ${year}. Accessed ${new Date().toLocaleDateString("en-US", { month: 'long', day: 'numeric', year: 'numeric' })}. ${url}`,
    mla: `${author}. "${title}." ${publisher}, ${year}, ${url}. accessed ${new Date().toLocaleDateString("en-US", { month: 'long', day: 'numeric', year: 'numeric' })}.`,
    apa: `${author} (${year}). *${title}*. ${publisher}. ${url}`
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Box border="all" padding={8} className={`aldine-bg-bone/20 aldine-border-bone aldine-mt-20 aldine-animate-in aldine-stagger-4 ${className}`}>
      <Row justify="between" align="baseline" className="aldine-mb-6 aldine-border-b aldine-border-ink-muted-alpha aldine-pb-4">
         <Ornament.Label className="aldine-accent">Bibliographic Record</Ornament.Label>
         <span className="aldine-text-[10px] aldine-font-mono aldine-ink-muted aldine-uppercase aldine-tracking-[0.3em]">Persistent Identifier: {id}</span>
      </Row>

      <Stack gap={8}>
         {Object.entries(citations).map(([key, val]) => (
            <Row key={key} gap={4} align="start" className="aldine-group">
               <span className="aldine-text-[9px] aldine-font-mono aldine-ink-muted aldine-uppercase aldine-tracking-widest aldine-w-16 aldine-pt-1 aldine-opacity-50">{key}</span>
               <p className="aldine-grow aldine-font-editorial aldine-text-base md:aldine-text-lg aldine-ink-base aldine-leading-relaxed aldine-italic group-hover:aldine-opacity-100 aldine-transition-opacity">
                 {val}
               </p>
               <button 
                  onClick={() => copyToClipboard(val)}
                  className="aldine-text-[9px] aldine-font-interface aldine-font-bold aldine-uppercase aldine-tracking-widest aldine-ink-muted hover:aldine-accent aldine-transition-colors aldine-pt-1"
               >
                  {copied ? "Copied" : "Copy"}
               </button>
            </Row>
         ))}
      </Stack>

      <Box className="aldine-mt-8 aldine-pt-4 aldine-border-t aldine-border-ink-muted-alpha/20 aldine-opacity-30">
         <p className="aldine-text-[9px] aldine-font-interface aldine-ink-muted aldine-uppercase aldine-tracking-[0.2em]">
            Digital Object synthesized for scholarly portability via OpenEtruscan Aldine Engine v1.0.
         </p>
      </Box>
    </Box>
  );
}




