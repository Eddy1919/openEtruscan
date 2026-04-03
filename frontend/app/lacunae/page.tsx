"use client";

import { useState } from "react";
import styles from "./page.module.css";
import { restoreLacunae, type RestoreResponse } from "@/lib/corpus";

const EXAMPLES = [
  { label: "Middle Gap", text: "suθi lar[..]al lecnes" },
  { label: "Missing Initial", text: "[.]i aviles" },
  { label: "Fragmentary", text: "m[.] api[..]" },
];

export default function LacunaePage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RestoreResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRestore = async (textToRestore: string) => {
    if (!textToRestore.trim()) {
      setResult(null);
      setError(null);
      return;
    }
    
    setLoading(true);
    setError(null);
    setResult(null);
    
    try {
      const response = await restoreLacunae(textToRestore, 5);
      setResult(response);
    } catch (err: any) {
      setError(err.message || "Failed to restore text.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      handleRestore(input);
    }
  };

  return (
    <div className="page-container" style={{ maxWidth: 900 }}>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: "2rem", marginBottom: "0.5rem" }}>
        Lacunae Restoration Tool
      </h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "2rem", lineHeight: 1.6 }}>
        Predict missing character sequences within epigraphic gaps using our Masked Language Model trained specifically on Old Italic orthography.
      </p>

      {error && (
        <div className={styles.errorBanner}>
          ⚠️ <strong>Error:</strong> {error}
        </div>
      )}

      <div className={styles.inputHeader}>
        <span className={styles.inputLabel}>TRANSLITERATED TEXT</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "var(--text-muted)" }}>
          Explicitly map gaps with <code style={{ color: "var(--accent)" }}>[.]</code> or <code style={{ color: "var(--accent)" }}>[..]</code>
        </span>
      </div>

      <textarea
        className="input"
        rows={4}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Enter text with lacunae, e.g. lar[..]i"
        style={{ fontFamily: "var(--font-mono)", fontSize: "1.1rem", resize: "vertical", marginBottom: "0.75rem" }}
      />

      <div className={styles.controlRow}>
        <button 
          className="btn btn-primary" 
          onClick={() => handleRestore(input)}
          disabled={loading || !input.trim()}
          style={{ marginRight: "1rem" }}
        >
          {loading ? "Predicting..." : "Restore"}
        </button>
        <button 
          className="btn btn-secondary" 
          onClick={() => { setInput(""); setResult(null); setError(null); }}
        >
          Clear
        </button>

        <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", marginLeft: "auto" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Try presets:</span>
          {EXAMPLES.map((ex) => (
            <button 
              key={ex.label} 
              className="btn btn-secondary" 
              style={{ fontSize: "0.7rem", padding: "0.3rem 0.7rem" }} 
              onClick={() => {
                setInput(ex.text);
                handleRestore(ex.text);
              }}
            >
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: "2rem" }}>
          <span className={styles.loadingText}>Running Neural Engine...</span>
        </div>
      )}

      {result && result.predictions && (
        <>
          <h3 style={{ fontFamily: "var(--font-mono)", fontSize: "0.9rem", color: "var(--text-muted)", marginBottom: "1rem", marginTop: "2rem" }}>
            PREDICTION RESULTS FOR <code>{result.text}</code>
          </h3>
          <div className={styles.outputGrid}>
            {result.predictions.map((pred, i) => (
              <div key={i} className="card">
                <div className={styles.cardHeader}>
                  <span className={styles.cardLabel}>POSITION {pred.position}</span>
                </div>
                <ul className={styles.probsList}>
                  {Object.entries(pred.predictions).map(([char, prob]) => {
                    const pct = Math.round(prob * 100);
                    return (
                      <li key={char} className={styles.probItem}>
                        <div className={styles.probRow}>
                          <span className={styles.charBox}>{char}</span>
                          <span className={styles.probScore}>{pct}%</span>
                        </div>
                        <div className={styles.probBarContainer}>
                          <div className={styles.probBar} style={{ width: `${pct}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
            {result.predictions.length === 0 && (
              <div className="card" style={{ gridColumn: "1 / -1" }}>
                <p style={{ color: "var(--text-secondary)", textAlign: "center" }}>
                  No explicit lacunae brackets found in the text.
                </p>
              </div>
            )}
          </div>
        </>
      )}

      <div style={{ marginTop: "4rem", paddingTop: "2rem", borderTop: "1px solid var(--border-color)" }}>
        <h2 style={{ fontSize: "1.2rem", marginBottom: "1rem" }}>Documentation</h2>
        <div style={{ color: "var(--text-secondary)", lineHeight: 1.6, fontSize: "0.9rem" }}>
          <p style={{ marginBottom: "1rem" }}>
            The OpenEtruscan Lacunae Restorer runs a Masked Language Model (MLM) built with 
            <code>torch.nn.TransformerEncoder</code>. This engine computes the mathematical probability distribution 
            for each obscured character based strictly on the surrounding epigraphic context.
          </p>
          <p style={{ marginBottom: "0.5rem" }}>
            <strong>Input Rules (Leiden Conventions):</strong>
          </p>
          <ul style={{ paddingLeft: "1.5rem", marginBottom: "1.5rem" }}>
            <li style={{ marginBottom: "0.5rem" }}>
              To ensure structural consistency, the system does <strong>not</strong> support generic, unbounded lacunae like <code>[...]</code>. Attempting to parse unpredictable void sizes via MLM introduces compounding historical inaccuracies.
            </li>
            <li>
              You must supply explicit representations corresponding to the physical missing space 
              by using one dot per discrete character. For example, <code>[.]</code> for one character, 
              and <code>[..]</code> for two characters. 
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
