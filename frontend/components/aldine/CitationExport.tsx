"use client";

import { useState } from "react";
import { Box, Row, Stack, Ornament } from "./Layout";

interface CitationProps {
  id: string;
  canonical: string;
  findspot: string | null;
  classification: string | null;
  dateApprox: number | null;
}

function toBibTeX(props: CitationProps): string {
  const year = props.dateApprox ? Math.abs(props.dateApprox) : null;
  const era = props.dateApprox && props.dateApprox < 0 ? " BCE" : props.dateApprox ? " CE" : "";
  const key = props.id.replace(/[\s.]/g, "_");
  return `@misc{openetruscan_${key},
  title     = {${props.id}: "${props.canonical}"},
  author    = {{OpenEtruscan Project}},
  year      = {2025},
  url       = {https://www.openetruscan.com/inscription/${encodeURIComponent(props.id)}},
  note      = {${props.findspot || "Unknown provenance"}${year ? `, ca. ${year}${era}` : ""}${props.classification ? `, ${props.classification}` : ""}}
}`;
}

function toCSLJSON(props: CitationProps): string {
  return JSON.stringify(
    [
      {
        type: "entry",
        id: `openetruscan_${props.id.replace(/[\s.]/g, "_")}`,
        title: `${props.id}: "${props.canonical}"`,
        author: [{ literal: "OpenEtruscan Project" }],
        issued: { "date-parts": [[2025]] },
        URL: `https://www.openetruscan.com/inscription/${encodeURIComponent(props.id)}`,
        note: [
          props.findspot || "Unknown provenance",
          props.classification,
          props.dateApprox
            ? `ca. ${Math.abs(props.dateApprox)} ${props.dateApprox < 0 ? "BCE" : "CE"}`
            : null,
        ]
          .filter(Boolean)
          .join(", "),
      },
    ],
    null,
    2
  );
}

/**
 * CitationExport: A systematic utility for generating academic citations.
 * Supports BibTeX and CSL-JSON formats for scholarly provenance tracking.
 */
export function AldineCitationExport(props: CitationProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="aldine-text-xs aldine-font-interface aldine-font-bold aldine-uppercase aldine-tracking-widest aldine-accent hover:aldine-ink-base aldine-transition-colors"
      >
        Cite this inscription
      </button>
    );
  }

  const bibtex = toBibTeX(props);
  const csljson = toCSLJSON(props);

  return (
    <Box border="all" surface="bone" padding={4} className="aldine-mt-4 aldine-shadow-sm aldine-rounded-xl">
      <Row justify="between" align="center" padding={2} className="aldine-mb-3">
        <Ornament.Label className="aldine-ink-muted">Citation Export</Ornament.Label>
        <button
          onClick={() => setOpen(false)}
          className="aldine-text-xs aldine-ink-muted hover:aldine-accent aldine-transition-colors"
        >
          Close
        </button>
      </Row>

      <Stack gap={6}>
        <Stack gap={2}>
          <Row justify="between" align="center">
            <span className="aldine-text-xs aldine-ink-muted aldine-font-bold aldine-uppercase aldine-tracking-widest">BibTeX</span>
            <button
              onClick={() => copy(bibtex, "bibtex")}
              className="aldine-text-xs aldine-font-interface aldine-font-bold aldine-accent aldine-px-2 aldine-py-1 aldine-bg-canvas aldine-rounded-xl aldine-border"
            >
              {copied === "bibtex" ? "Copied" : "Copy"}
            </button>
          </Row>
          <Box as="pre" padding={3} surface="canvas" border="all" className="aldine-rounded-xl aldine-text-xs aldine-font-mono aldine-ink-base aldine-overflow-x-auto aldine-whitespace-pre-wrap">
            {bibtex}
          </Box>
        </Stack>

        <Stack gap={2}>
          <Row justify="between" align="center">
            <span className="aldine-text-xs aldine-ink-muted aldine-font-bold aldine-uppercase aldine-tracking-widest">CSL-JSON</span>
            <button
              onClick={() => copy(csljson, "csl")}
              className="aldine-text-xs aldine-font-interface aldine-font-bold aldine-accent aldine-px-2 aldine-py-1 aldine-bg-canvas aldine-rounded-xl aldine-border"
            >
              {copied === "csl" ? "Copied" : "Copy"}
            </button>
          </Row>
          <Box as="pre" padding={3} surface="canvas" border="all" className="aldine-rounded-xl aldine-text-xs aldine-font-mono aldine-ink-base aldine-overflow-x-auto aldine-whitespace-pre-wrap">
            {csljson}
          </Box>
        </Stack>
      </Stack>
    </Box>
  );
}

