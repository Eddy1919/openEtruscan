"use client";

import { useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import type { KWICRow } from "@/lib/corpus";
import { fetchConcordance } from "@/lib/corpus";
import styles from "./page.module.css";

type SortKey = "left" | "right" | "id";

const CONTEXT_OPTIONS = [20, 40, 60, 80];

export default function ConcordancePage() {
  const [rows, setRows] = useState<KWICRow[]>([]);
  const [uniqueCount, setUniqueCount] = useState(0);
  const [query, setQuery] = useState("");
  const [contextLen, setContextLen] = useState(40);
  const [sortBy, setSortBy] = useState<SortKey>("left");
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  const doSearch = useCallback(
    (q: string, ctx: number) => {
      const trimmed = q.trim();
      if (trimmed.length < 2) {
        setRows([]);
        setUniqueCount(0);
        setSearched(trimmed.length > 0);
        return;
      }
      setLoading(true);
      setSearched(true);
      fetchConcordance(trimmed, ctx)
        .then((res) => {
          setRows(res.rows);
          setUniqueCount(res.unique_inscriptions);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    },
    []
  );

  // Debounced search on query or context change
  const triggerSearch = useCallback(
    (q: string, ctx: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(q, ctx), 400);
    },
    [doSearch]
  );

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

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>
      <h1 className={styles.heading}>Concordance</h1>
      <p className={styles.subtitle}>
        Enter a term to see every occurrence in context across the corpus.
        Minimum 2 characters.
      </p>

      {/* Controls */}
      <div className={styles.controls}>
        <input
          type="text"
          className={`input ${styles.searchInput}`}
          placeholder="e.g. turce, avil, laris, mi"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            triggerSearch(e.target.value, contextLen);
          }}
        />
        <div className={styles.controlRow}>
          <div className={styles.controlGroup}>
            <label className={styles.controlLabel}>Context</label>
            <select
              className={`input ${styles.selectSmall}`}
              value={contextLen}
              onChange={(e) => {
                const ctx = Number(e.target.value);
                setContextLen(ctx);
                triggerSearch(query, ctx);
              }}
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
              in {uniqueCount.toLocaleString()} inscription{uniqueCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div className="loading-shimmer" style={{ height: 200 }} />
      )}

      {/* KWIC table */}
      {!loading && sorted.length > 0 && (
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

      {!loading && searched && sorted.length === 0 && query.trim().length >= 2 && (
        <p className={styles.noResults}>
          No occurrences of &quot;{query}&quot; found in the corpus.
        </p>
      )}

      {searched && query.trim().length < 2 && query.trim().length > 0 && (
        <p className={styles.noResults}>
          Enter at least 2 characters to search.
        </p>
      )}
    </div>
  );
}
