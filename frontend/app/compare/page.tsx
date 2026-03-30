"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import type { Inscription } from "@/lib/corpus";
import { fetchInscription, fetchIds, toOldItalic, dateDisplay, CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";

export default function ComparePage() {
  const [allIds, setAllIds] = useState<string[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [left, setLeft] = useState<Inscription | null>(null);
  const [right, setRight] = useState<Inscription | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchIds()
      .then((ids) => setAllIds(ids.sort()))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Fetch individual inscriptions when IDs change
  const fetchSide = useCallback(async (id: string) => {
    if (!id) return null;
    try {
      return await fetchInscription(id);
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    fetchSide(leftId).then(setLeft);
  }, [leftId, fetchSide]);

  useEffect(() => {
    fetchSide(rightId).then(setRight);
  }, [rightId, fetchSide]);

  // Character-level diff
  function charDiff(a: string, b: string) {
    const maxLen = Math.max(a.length, b.length);
    const result: { char: string; type: "same" | "diff" | "extra" }[] = [];
    for (let i = 0; i < maxLen; i++) {
      if (i >= a.length) {
        result.push({ char: b[i], type: "extra" });
      } else if (i >= b.length) {
        result.push({ char: a[i], type: "extra" });
      } else if (a[i] === b[i]) {
        result.push({ char: a[i], type: "same" });
      } else {
        result.push({ char: a[i], type: "diff" });
      }
    }
    return result;
  }

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 200 }} />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>
      <h1 className={styles.heading}>Compare Inscriptions</h1>
      <p className={styles.subtitle}>
        Select two inscriptions to view side-by-side with character-level
        differences highlighted. Useful for studying formulaic patterns and
        scribal variation.
      </p>

      <div className={styles.selectors}>
        <div className={styles.selectorGroup}>
          <label className={styles.selectorLabel}>Inscription A</label>
          <input
            list="ids-left"
            className={`input ${styles.selectorInput}`}
            placeholder="Type inscription ID"
            value={leftId}
            onChange={(e) => setLeftId(e.target.value)}
          />
          <datalist id="ids-left">
            {allIds.map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
        </div>
        <div className={styles.selectorGroup}>
          <label className={styles.selectorLabel}>Inscription B</label>
          <input
            list="ids-right"
            className={`input ${styles.selectorInput}`}
            placeholder="Type inscription ID"
            value={rightId}
            onChange={(e) => setRightId(e.target.value)}
          />
          <datalist id="ids-right">
            {allIds.map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
        </div>
      </div>

      {left && right && (
        <>
          <div className={styles.compareGrid}>
            {/* Left card */}
            <div className="card">
              <div className={styles.cardHead}>
                <span className={styles.cardId}>{left.id}</span>
                <span
                  className={styles.cardBadge}
                  style={{ color: CLASS_COLORS[left.classification || "unknown"] }}
                >
                  {left.classification || "unknown"}
                </span>
              </div>
              <p className={styles.oldItalic}>
                {left.old_italic || toOldItalic(left.canonical)}
              </p>
              <p className={styles.canonical}>{left.canonical}</p>
              <div className={styles.meta}>
                <span>{left.findspot || "Unknown"}</span>
                <span>{dateDisplay(left)}</span>
              </div>
            </div>

            {/* Right card */}
            <div className="card">
              <div className={styles.cardHead}>
                <span className={styles.cardId}>{right.id}</span>
                <span
                  className={styles.cardBadge}
                  style={{ color: CLASS_COLORS[right.classification || "unknown"] }}
                >
                  {right.classification || "unknown"}
                </span>
              </div>
              <p className={styles.oldItalic}>
                {right.old_italic || toOldItalic(right.canonical)}
              </p>
              <p className={styles.canonical}>{right.canonical}</p>
              <div className={styles.meta}>
                <span>{right.findspot || "Unknown"}</span>
                <span>{dateDisplay(right)}</span>
              </div>
            </div>
          </div>

          {/* Diff view */}
          <div className="card" style={{ marginTop: "1rem" }}>
            <h3 className={styles.diffTitle}>Character-Level Difference</h3>
            <div className={styles.diffRow}>
              <div>
                <span className={styles.diffLabel}>A</span>
                <span className={styles.diffChars}>
                  {charDiff(left.canonical, right.canonical).map((d, i) => (
                    <span
                      key={i}
                      className={
                        d.type === "same"
                          ? styles.charSame
                          : d.type === "diff"
                            ? styles.charDiff
                            : styles.charExtra
                      }
                    >
                      {d.char}
                    </span>
                  ))}
                </span>
              </div>
              <div>
                <span className={styles.diffLabel}>B</span>
                <span className={styles.diffChars}>
                  {charDiff(right.canonical, left.canonical).map((d, i) => (
                    <span
                      key={i}
                      className={
                        d.type === "same"
                          ? styles.charSame
                          : d.type === "diff"
                            ? styles.charDiff
                            : styles.charExtra
                      }
                    >
                      {d.char}
                    </span>
                  ))}
                </span>
              </div>
            </div>
            <div className={styles.diffLegend}>
              <span><span className={styles.charSame}>a</span> Match</span>
              <span><span className={styles.charDiff}>a</span> Changed</span>
              <span><span className={styles.charExtra}>a</span> Extra</span>
            </div>
          </div>
        </>
      )}

      {(leftId || rightId) && (!left || !right) && (
        <p className={styles.noResults}>
          {!left && leftId ? `Inscription "${leftId}" not found. ` : ""}
          {!right && rightId ? `Inscription "${rightId}" not found.` : ""}
        </p>
      )}
    </div>
  );
}
