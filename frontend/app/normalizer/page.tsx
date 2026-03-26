"use client";

import { useState } from "react";

// Simplified normalizer — port of the original web/app.js logic
const CANONICAL_MAP: Record<string, string> = {
  θ: "th", φ: "ph", χ: "ch", ś: "sh", c: "k", q: "k",
};

function toPhonetic(canonical: string): string {
  let result = "";
  for (const ch of canonical.toLowerCase()) {
    result += CANONICAL_MAP[ch] || ch;
  }
  return result;
}

export default function NormalizerPage() {
  const [input, setInput] = useState("");

  const canonical = input.toLowerCase().trim();
  const phonetic = toPhonetic(canonical);

  return (
    <div className="page-container" style={{ maxWidth: 700 }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "2rem",
          marginBottom: "0.5rem",
        }}
      >
        Script Normalizer
      </h1>
      <p
        style={{
          color: "var(--text-secondary)",
          marginBottom: "2rem",
          lineHeight: 1.6,
        }}
      >
        Convert Etruscan text between transcription systems. Enter text in any
        supported format to see all five representations.
      </p>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <label
          style={{
            fontSize: "0.75rem",
            fontWeight: 600,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            display: "block",
            marginBottom: "0.5rem",
          }}
        >
          Input text
        </label>
        <textarea
          className="input"
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter Etruscan text, e.g. mi aviles"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "1.1rem",
            resize: "vertical",
          }}
        />
      </div>

      {canonical && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div className="card">
            <label
              style={{
                fontSize: "0.7rem",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
              }}
            >
              Canonical
            </label>
            <p className="inscription-text" style={{ fontSize: "1.2rem" }}>
              {canonical}
            </p>
          </div>
          <div className="card">
            <label
              style={{
                fontSize: "0.7rem",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
              }}
            >
              Phonetic
            </label>
            <p className="inscription-text" style={{ fontSize: "1.2rem" }}>
              {phonetic}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
