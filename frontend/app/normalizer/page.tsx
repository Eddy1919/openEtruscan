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
import styles from "./page.module.css";

const EXAMPLES = [
  { label: "CIE", text: "MI AVILES" },
  { label: "Philological", text: "laris θanχvilus" },
  { label: "Old Italic", text: "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔" },
  { label: "Web-safe", text: "laris thankhvilus" },
];

export default function NormalizerPage() {
  const [ready, setReady] = useState(false);
  const [input, setInput] = useState("");
  const [langId, setLangId] = useState("etruscan");
  const [langs, setLangs] = useState<Record<string, LanguageData> | null>(null);
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
    <div className="page-container" style={{ maxWidth: 900 }}>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: "2rem", marginBottom: "0.5rem" }}>
        Script Normalizer
      </h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "2rem", lineHeight: 1.6 }}>
        Convert Etruscan text between five transcription systems. Enter text in
        any supported format to see all representations.
      </p>

      {/* Input row: label + detected badge + language selector */}
      <div className={styles.inputHeader}>
        <span className={styles.inputLabel}>INPUT</span>
        {result?.source_system && (
          <span className="badge badge-accent" style={{ fontSize: "0.65rem" }}>
            Detected: {SOURCE_SYSTEM_NAMES[result.source_system] || result.source_system}
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Language:
          </span>
          <select className="input" style={{ width: "auto" }} value={langId} onChange={(e) => handleLangChange(e.target.value)}>
            {langs && Object.entries(langs).map(([id, lang]) => (
              <option key={id} value={id}>{lang.displayName}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Input textarea */}
      <textarea
        className="input"
        rows={4}
        value={input}
        onChange={(e) => handleInput(e.target.value)}
        placeholder="Enter Etruscan text, e.g. mi aviles"
        style={{ fontFamily: "var(--font-mono)", fontSize: "1.1rem", resize: "vertical", marginBottom: "0.75rem" }}
      />

      {/* Clear + examples row */}
      <div className={styles.controlRow}>
        <button className="btn btn-secondary" style={{ fontSize: "0.8rem" }} onClick={() => { setInput(""); setResult(null); }}>
          Clear
        </button>
        <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", marginLeft: "auto" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Try:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex.label} className="btn btn-secondary" style={{ fontSize: "0.7rem", padding: "0.3rem 0.7rem" }} onClick={() => handleInput(ex.text)}>
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      {/* Output: 2×2 grid matching old design */}
      {result && (
        <>
          <div className={styles.outputGrid}>
            <div className="card">
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>CANONICAL</span>
                <button onClick={() => copyToClipboard(result.canonical)} className={styles.copyBtn} title="Copy">📋</button>
              </div>
              <p className="inscription-text" style={{ fontSize: "1.2rem" }}>{result.canonical || "—"}</p>
              <p className={styles.cardDesc}>Standardized philological form</p>
            </div>

            <div className="card">
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>OLD ITALIC UNICODE</span>
                <button onClick={() => copyToClipboard(result.old_italic)} className={styles.copyBtn} title="Copy">📋</button>
              </div>
              <p className="inscription-text" style={{ fontSize: "1.4rem" }}>{result.old_italic || "—"}</p>
              <p className={styles.cardDesc}>Unicode U+10300 block</p>
            </div>

            <div className="card">
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>PHONETIC (IPA)</span>
                <button onClick={() => copyToClipboard(result.phonetic)} className={styles.copyBtn} title="Copy">📋</button>
              </div>
              <p className="inscription-text" style={{ fontSize: "1.2rem" }}>{result.phonetic || "—"}</p>
              <p className={styles.cardDesc}>International Phonetic Alphabet</p>
            </div>

            <div className="card">
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>TOKENS</span>
              </div>
              <p className="inscription-text" style={{ fontSize: "1.2rem" }}>
                {result.tokens.map((t) => `[${t}]`).join(" ") || "—"}
              </p>
              <p className={styles.cardDesc}>Word segmentation</p>
            </div>
          </div>

          {/* Confidence bar */}
          <div className="card" style={{ marginTop: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.4rem" }}>
              <span className={styles.cardLabel}>CONFIDENCE</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: confColor }}>{confPct}%</span>
            </div>
            <div style={{ height: 6, background: "var(--bg-primary)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${confPct}%`, height: "100%", background: confColor, borderRadius: 3, transition: "width 0.3s ease" }} />
            </div>
          </div>

          {result.warnings.length > 0 && (
            <div style={{ padding: "0.75rem 1rem", marginTop: "0.75rem", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.2)", borderRadius: 8, fontSize: "0.8rem", color: "var(--danger)" }}>
              ⚠️ {result.warnings.join(" | ")}
            </div>
          )}
        </>
      )}
    </div>
  );
}
