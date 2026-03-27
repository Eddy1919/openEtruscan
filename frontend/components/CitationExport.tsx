"use client";

import { useState } from "react";

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

export default function CitationExport(props: CitationProps) {
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
        className="btn btn-secondary"
        style={{ fontSize: "0.8rem" }}
        onClick={() => setOpen(true)}
      >
        Cite this inscription
      </button>
    );
  }

  const bibtex = toBibTeX(props);
  const csljson = toCSLJSON(props);

  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
        <h3 style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
          Citation
        </h3>
        <button
          onClick={() => setOpen(false)}
          style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.8rem" }}
        >
          Close
        </button>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>BibTeX</span>
          <button
            onClick={() => copy(bibtex, "bibtex")}
            className="btn btn-secondary"
            style={{ fontSize: "0.7rem", padding: "0.25rem 0.6rem" }}
          >
            {copied === "bibtex" ? "Copied" : "Copy"}
          </button>
        </div>
        <pre style={{
          background: "var(--bg-primary)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "0.75rem",
          fontFamily: "var(--font-mono)",
          fontSize: "0.72rem",
          color: "var(--accent-light)",
          overflowX: "auto",
          whiteSpace: "pre-wrap",
        }}>
          {bibtex}
        </pre>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>CSL-JSON</span>
          <button
            onClick={() => copy(csljson, "csl")}
            className="btn btn-secondary"
            style={{ fontSize: "0.7rem", padding: "0.25rem 0.6rem" }}
          >
            {copied === "csl" ? "Copied" : "Copy"}
          </button>
        </div>
        <pre style={{
          background: "var(--bg-primary)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "0.75rem",
          fontFamily: "var(--font-mono)",
          fontSize: "0.72rem",
          color: "var(--accent-light)",
          overflowX: "auto",
          whiteSpace: "pre-wrap",
        }}>
          {csljson}
        </pre>
      </div>
    </div>
  );
}
