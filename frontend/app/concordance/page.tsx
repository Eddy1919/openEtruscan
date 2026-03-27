"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import type { Inscription } from "@/lib/corpus";
import { loadCorpus } from "@/lib/corpus";
import styles from "./page.module.css";

interface KWICRow {
  inscId: string;
  left: string;
  keyword: string;
  right: string;
}

type SortKey = "left" | "right" | "id";

const CONTEXT_OPTIONS = [20, 40, 60, 80];

export default function ConcordancePage() {
  const [corpus, setCorpus] = useState<Inscription[]>([]);
  const [query, setQuery] = useState("");
  const [contextLen, setContextLen] = useState(40);
  const [sortBy, setSortBy] = useState<SortKey>("left");

  useEffect(() => {
    loadCorpus().then(setCorpus);
  }, []);

  const queryLower = query.toLowerCase().trim();

  const rows = useMemo((): KWICRow[] => {
    if (!queryLower || queryLower.length < 2) return [];

    const results: KWICRow[] = [];
    for (const insc of corpus) {
      const text = insc.canonical.toLowerCase();
      let startPos = 0;
      let idx: number;

      while ((idx = text.indexOf(queryLower, startPos)) !== -1) {
        const matchStart = idx;
        const matchEnd = idx + queryLower.length;
        const original = insc.canonical;

        const leftFull = original.slice(0, matchStart);
        const left = leftFull.length > contextLen
          ? leftFull.slice(-contextLen)
          : leftFull;

        const rightFull = original.slice(matchEnd);
        const right = rightFull.length > contextLen
          ? rightFull.slice(0, contextLen)
          : rightFull;

        results.push({
          inscId: insc.id,
          left,
          keyword: original.slice(matchStart, matchEnd),
          right,
        });

        startPos = matchEnd;
      }
    }

    return results;
  }, [corpus, queryLower, contextLen]);

  const sorted = useMemo(() => {
    const arr = [...rows];
    switch (sortBy) {
      case "left":
        return arr.sort((a, b) => {
          const aEnd = a.left.trim().split(/\s+/).pop() || "";
          const bEnd = b.left.trim().split(/\s+/).pop() || "";
          return aEnd.localeCompare(bEnd);
        });
      case "right":
        return arr.sort((a, b) => {
          const aStart = a.right.trim().split(/\s+/)[0] || "";
          const bStart = b.right.trim().split(/\s+/)[0] || "";
          return aStart.localeCompare(bStart);
        });
      case "id":
        return arr.sort((a, b) => a.inscId.localeCompare(b.inscId));
      default:
        return arr;
    }
  }, [rows, sortBy]);

  const uniqueInscriptions = useMemo(() => {
    return new Set(rows.map((r) => r.inscId)).size;
  }, [rows]);

  if (!corpus.length) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 200 }} />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>
      <h1 className={styles.heading}>Concordance</h1>
      <p className={styles.subtitle}>
        Enter a term to see every occurrence in context across{" "}
        {corpus.length.toLocaleString()} inscriptions. Minimum 2 characters.
      </p>

      {/* Controls */}
      <div className={styles.controls}>
        <input
          type="text"
          className={`input ${styles.searchInput}`}
          placeholder="e.g. turce, avil, laris, mi"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className={styles.controlRow}>
          <div className={styles.controlGroup}>
            <label className={styles.controlLabel}>Context</label>
            <select
              className={`input ${styles.selectSmall}`}
              value={contextLen}
              onChange={(e) => setContextLen(Number(e.target.value))}
            >
              {CONTEXT_OPTIONS.map((n) => (
                <option key={n} value={n}>{n} chars</option>
              ))}
            </select>
          </div>
          <div className={styles.controlGroup}>
            <label className={styles.controlLabel}>Sort by</label>
            <select
              className={`input ${styles.selectSmall}`}
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
            >
              <option value="left">Left context</option>
              <option value="right">Right context</option>
              <option value="id">Inscription ID</option>
            </select>
          </div>
          {rows.length > 0 && (
            <span className={styles.resultCount}>
              {rows.length.toLocaleString()} occurrence{rows.length !== 1 ? "s" : ""}{" "}
              in {uniqueInscriptions.toLocaleString()} inscription{uniqueInscriptions !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* KWIC table */}
      {queryLower.length >= 2 && sorted.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.kwicTable}>
            <thead>
              <tr>
                <th className={styles.thId}>ID</th>
                <th className={styles.thLeft}>Left context</th>
                <th className={styles.thKw}>Keyword</th>
                <th className={styles.thRight}>Right context</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr key={`${row.inscId}-${i}`}>
                  <td className={styles.tdId}>
                    <Link href={`/inscription/${encodeURIComponent(row.inscId)}`}>
                      {row.inscId}
                    </Link>
                  </td>
                  <td className={styles.tdLeft}>{row.left}</td>
                  <td className={styles.tdKw}>{row.keyword}</td>
                  <td className={styles.tdRight}>{row.right}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {queryLower.length >= 2 && sorted.length === 0 && (
        <p className={styles.noResults}>
          No occurrences of &quot;{query}&quot; found in the corpus.
        </p>
      )}

      {queryLower.length < 2 && queryLower.length > 0 && (
        <p className={styles.noResults}>
          Enter at least 2 characters to search.
        </p>
      )}
    </div>
  );
}
