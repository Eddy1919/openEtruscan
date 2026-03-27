"use client";

import { useState, useCallback } from "react";
import {
  loadAndClassify,
  CLASS_DESCRIPTIONS,
  type ClassifierOutput,
} from "@/lib/classifier";
import { CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";

const EXAMPLES = [
  { text: "mi araθia velθurus", desc: "Ownership mark" },
  { text: "arnθ cutnas zilcte lupu", desc: "Funerary (magistrate death)" },
  { text: "turce menrvas alpan", desc: "Votive offering" },
  { text: "tular rasna spural", desc: "Boundary marker" },
  { text: "tinia uni menerva", desc: "Dedicatory (Capitoline triad)" },
  { text: "zilχ marunuχ cepen tenu", desc: "Legal (magistrate titles)" },
  { text: "zal ci pruχ aska", desc: "Commercial (trade goods)" },
];

export default function ClassifierPage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [cnnResult, setCnnResult] = useState<ClassifierOutput | null>(null);
  const [tfResult, setTfResult] = useState<ClassifierOutput | null>(null);
  const [error, setError] = useState<string | null>(null);

  const classify = useCallback(async (text: string) => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setCnnResult(null);
    setTfResult(null);

    try {
      const [cnn, tf] = await Promise.all([
        loadAndClassify(text, "cnn"),
        loadAndClassify(text, "transformer"),
      ]);
      setCnnResult(cnn);
      setTfResult(tf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Classification failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = () => classify(input);
  const handleExample = (text: string) => {
    setInput(text);
    classify(text);
  };

  return (
    <div className="page-container" style={{ maxWidth: 1000 }}>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: "2rem", marginBottom: "0.5rem" }}>
        Inscription Classifier
      </h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem", lineHeight: 1.6 }}>
        Classify Etruscan inscriptions by epigraphic type. Two neural
        architectures, a character-level CNN and a Transformer encoder, run
        side-by-side via ONNX Runtime (WASM). All inference is client-side.
      </p>

      {/* Input */}
      <div className="card" style={{ marginBottom: "1rem" }}>
        <label className={styles.label}>Inscription text</label>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <input
            className="input"
            style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: "1rem" }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="e.g. mi araθia velθurus"
          />
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={loading || !input.trim()}
          >
            {loading ? "Running…" : "Classify"}
          </button>
        </div>
      </div>

      {/* Examples */}
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "2rem" }}>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", alignSelf: "center" }}>
          Examples:
        </span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.text}
            className="btn btn-secondary"
            style={{ fontSize: "0.7rem", padding: "0.25rem 0.6rem" }}
            onClick={() => handleExample(ex.text)}
            title={ex.desc}
          >
            {ex.text}
          </button>
        ))}
      </div>

      {error && (
        <div
          style={{
            padding: "0.75rem 1rem",
            background: "rgba(248,113,113,0.1)",
            border: "1px solid rgba(248,113,113,0.2)",
            borderRadius: 8,
            fontSize: "0.85rem",
            color: "var(--danger)",
            marginBottom: "1.5rem",
          }}
        >
          {error}
        </div>
      )}

      {/* Side-by-side results */}
      {(cnnResult || tfResult) && (
        <div className={styles.comparison}>
          {cnnResult && <ModelResultCard result={cnnResult} />}
          {tfResult && <ModelResultCard result={tfResult} />}
        </div>
      )}

      {/* Agreement / disagreement indicator */}
      {cnnResult && tfResult && (
        <div className={styles.agreement}>
          {cnnResult.predictions[0].label === tfResult.predictions[0].label ? (
            <span style={{ color: "var(--success)" }}>
              Both models agree: <strong>{cnnResult.predictions[0].label}</strong>
            </span>
          ) : (
            <span style={{ color: "var(--warning)" }}>
              Models disagree. CNN: <strong>{cnnResult.predictions[0].label}</strong>
              {" "}vs Transformer: <strong>{tfResult.predictions[0].label}</strong>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ModelResultCard({ result }: { result: ClassifierOutput }) {
  const top = result.predictions[0];
  const topColor = CLASS_COLORS[top.label] || CLASS_COLORS.unknown;

  return (
    <div className="card">
      <div className={styles.modelHeader}>
        <span className={styles.modelName}>{result.arch}</span>
        <span className={styles.inferenceTime}>
          {result.inferenceMs.toFixed(0)} ms
        </span>
      </div>

      {/* Top prediction */}
      <div className={styles.topPrediction}>
        <span className={styles.topLabel} style={{ color: topColor }}>
          {top.label.toUpperCase()}
        </span>
        <span className={styles.topConf}>
          {(top.probability * 100).toFixed(1)}%
        </span>
      </div>
      <p className={styles.typeDesc}>
        {CLASS_DESCRIPTIONS[top.label] || ""}
      </p>

      {/* Full distribution */}
      <div className={styles.bars}>
        {result.predictions.map(({ label, probability }) => {
          const color = CLASS_COLORS[label] || CLASS_COLORS.unknown;
          const pct = probability * 100;
          return (
            <div key={label} className={styles.barRow}>
              <span className={styles.barLabel}>{label}</span>
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{ width: `${Math.max(1, pct)}%`, background: color }}
                />
              </div>
              <span className={styles.barPct} style={{ color }}>
                {pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
