"use client";

import { useEffect, useState, useCallback } from "react";
import {
  loadLanguages,
  normalize,
  switchLanguage,
  getLanguages,
  SOURCE_SYSTEM_NAMES,
  type NormalizeResult,
  type LanguageData,
} from "@/lib/normalizer";

const EXAMPLES = [
  { label: "mi aviles", text: "mi aviles" },
  { label: "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔", text: "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔" },
  { label: "MI AVILES (CIE)", text: "MI AVILES" },
  { label: "laris θanχvilus", text: "laris θanχvilus" },
  { label: "laris thankhvilus", text: "laris thankhvilus" },
];

export default function NormalizerPage() {
  const [ready, setReady] = useState(false);
  const [input, setInput] = useState("");
  const [langId, setLangId] = useState("etruscan");
  const [langs, setLangs] = useState<Record<string, LanguageData> | null>(
    null
  );
  const [result, setResult] = useState<NormalizeResult | null>(null);

  useEffect(() => {
    loadLanguages().then((l) => {
      setLangs(l);
      setReady(true);
    });
  }, []);

  const handleInput = useCallback(
    (text: string) => {
      setInput(text);
      if (!ready || !text.trim()) {
        setResult(null);
        return;
      }
      setResult(normalize(text));
    },
    [ready]
  );

  const handleLangChange = useCallback(
    (id: string) => {
      setLangId(id);
      switchLanguage(id);
      if (input.trim()) {
        setResult(normalize(input));
      }
    },
    [input]
  );

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // fallback
    }
  };

  const confPct = result ? Math.round(result.confidence * 100) : 0;
  const confColor =
    confPct >= 80
      ? "var(--success)"
      : confPct >= 50
        ? "var(--warning)"
        : "var(--danger)";

  return (
    <div className="page-container" style={{ maxWidth: 800 }}>
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
        Convert Etruscan text between five transcription systems. Enter text in
        any supported format to see all representations.
      </p>

      {/* Language selector */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          alignItems: "flex-end",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ flex: 1 }}>
          <label
            style={{
              fontSize: "0.7rem",
              fontWeight: 600,
              color: "var(--text-muted)",
              textTransform: "uppercase" as const,
              letterSpacing: "0.5px",
              display: "block",
              marginBottom: "0.3rem",
            }}
          >
            Language
          </label>
          <select
            className="input"
            value={langId}
            onChange={(e) => handleLangChange(e.target.value)}
          >
            {langs &&
              Object.entries(langs).map(([id, lang]) => (
                <option key={id} value={id}>
                  {lang.displayName}
                </option>
              ))}
          </select>
        </div>
        <button
          className="btn btn-secondary"
          onClick={() => {
            setInput("");
            setResult(null);
          }}
        >
          Clear
        </button>
      </div>

      {/* Input */}
      <div className="card" style={{ marginBottom: "1rem" }}>
        <label
          style={{
            fontSize: "0.7rem",
            fontWeight: 600,
            color: "var(--text-muted)",
            textTransform: "uppercase" as const,
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
          onChange={(e) => handleInput(e.target.value)}
          placeholder="Enter Etruscan text, e.g. mi aviles"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "1.1rem",
            resize: "vertical",
          }}
        />
      </div>

      {/* Example buttons */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          marginBottom: "1.5rem",
        }}
      >
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            alignSelf: "center",
          }}
        >
          Try:
        </span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            className="btn btn-secondary"
            style={{ fontSize: "0.75rem", padding: "0.35rem 0.8rem" }}
            onClick={() => handleInput(ex.text)}
          >
            {ex.label}
          </button>
        ))}
      </div>

      {/* Output */}
      {result && (
        <>
          {/* Detected system badge */}
          {result.source_system && (
            <div
              style={{
                marginBottom: "1rem",
                fontSize: "0.8rem",
                color: "var(--text-secondary)",
              }}
            >
              Detected:{" "}
              <span className="badge badge-accent">
                {SOURCE_SYSTEM_NAMES[result.source_system] ||
                  result.source_system}
              </span>
            </div>
          )}

          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
          >
            {/* Canonical */}
            <OutputCard
              label="Canonical"
              value={result.canonical}
              onCopy={() => copyToClipboard(result.canonical)}
            />

            {/* Old Italic */}
            <OutputCard
              label="Old Italic Unicode"
              value={result.old_italic}
              onCopy={() => copyToClipboard(result.old_italic)}
              large
            />

            {/* Phonetic */}
            <OutputCard
              label="Phonetic (IPA)"
              value={result.phonetic}
              onCopy={() => copyToClipboard(result.phonetic)}
            />

            {/* Tokens */}
            <OutputCard
              label="Tokens"
              value={result.tokens.map((t) => `[${t}]`).join(" ")}
            />

            {/* Confidence */}
            <div className="card">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "0.5rem",
                }}
              >
                <label
                  style={{
                    fontSize: "0.7rem",
                    color: "var(--text-muted)",
                    textTransform: "uppercase" as const,
                    letterSpacing: "0.5px",
                  }}
                >
                  Confidence
                </label>
                <span
                  style={{ fontSize: "0.85rem", fontWeight: 600, color: confColor }}
                >
                  {confPct}%
                </span>
              </div>
              <div
                style={{
                  height: 6,
                  background: "var(--bg-primary)",
                  borderRadius: 3,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${confPct}%`,
                    height: "100%",
                    background: confColor,
                    borderRadius: 3,
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </div>

            {/* Warnings */}
            {result.warnings.length > 0 && (
              <div
                style={{
                  padding: "0.75rem 1rem",
                  background: "rgba(248, 113, 113, 0.1)",
                  border: "1px solid rgba(248, 113, 113, 0.2)",
                  borderRadius: 8,
                  fontSize: "0.8rem",
                  color: "var(--danger)",
                }}
              >
                ⚠️ {result.warnings.join(" | ")}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function OutputCard({
  label,
  value,
  onCopy,
  large,
}: {
  label: string;
  value: string;
  onCopy?: () => void;
  large?: boolean;
}) {
  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.35rem",
        }}
      >
        <label
          style={{
            fontSize: "0.7rem",
            color: "var(--text-muted)",
            textTransform: "uppercase" as const,
            letterSpacing: "0.5px",
          }}
        >
          {label}
        </label>
        {onCopy && (
          <button
            onClick={onCopy}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: "0.9rem",
              opacity: 0.5,
            }}
            title="Copy"
          >
            📋
          </button>
        )}
      </div>
      <p
        className="inscription-text"
        style={{ fontSize: large ? "1.4rem" : "1.1rem" }}
      >
        {value || "—"}
      </p>
    </div>
  );
}
