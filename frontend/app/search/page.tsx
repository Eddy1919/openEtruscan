"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import type { Inscription, StatsSummary } from "@/lib/corpus";
import { searchCorpus, fetchStatsSummary, toOldItalic, dateDisplay, CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";

const CLASSIFICATIONS = [
  "funerary", "votive", "dedicatory", "legal",
  "commercial", "boundary", "ownership", "unknown",
];

const PAGE_SIZE = 50;

type SortKey = "relevance" | "date" | "site" | "id";

export default function SearchPage() {
  const [results, setResults] = useState<Inscription[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [activeClass, setActiveClass] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortKey>("relevance");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [offset, setOffset] = useState(0);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch stats for facet counts
  useEffect(() => {
    fetchStatsSummary().then(setStats).catch(console.error);
  }, []);

  // Debounced search
  const doSearch = useCallback(
    (text: string, classification: string | null, sortKey: SortKey, newOffset: number) => {
      setLoading(true);
      searchCorpus({
        text: text || undefined,
        classification: classification || undefined,
        limit: PAGE_SIZE,
        offset: newOffset,
        sort_by: sortKey,
      })
        .then((res) => {
          if (newOffset === 0) {
            setResults(res.results);
          } else {
            setResults((prev) => [...prev, ...res.results]);
          }
          setTotal(res.total);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    },
    []
  );

  // Initial load
  useEffect(() => {
    doSearch("", null, "relevance", 0);
  }, [doSearch]);

  // Trigger search on query or filter change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      doSearch(query, activeClass, sortBy, 0);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, activeClass, sortBy, doSearch]);

  const sorted = results; // the backend returns results pre-sorted correctly

  const facets = useMemo(() => {
    if (!stats) return [];
    return CLASSIFICATIONS
      .map((cls) => ({
        cls,
        count: stats.classification_counts.find(([c]) => c === cls)?.[1] || 0,
      }))
      .filter((f) => f.count > 0);
  }, [stats]);

  const handleLoadMore = () => {
    const nextOffset = offset + PAGE_SIZE;
    setOffset(nextOffset);
    doSearch(query, activeClass, sortBy, nextOffset);
  };

  if (loading && results.length === 0) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 200 }} />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>
      <h1 className={styles.heading}>Search the Corpus</h1>
      <p className={styles.subtitle}>
        Query {(stats?.total || total).toLocaleString()} inscriptions by text, identifier,
        findspot, or Old Italic Unicode.
      </p>

      {/* Search input */}
      <div className={styles.searchBar}>
        <input
          type="text"
          className={`input ${styles.searchInput}`}
          placeholder="e.g. laris, turce, Volsinii, Cr 2.20"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className={styles.sortRow}>
          <span className={styles.resultCount}>
            {total.toLocaleString()} result{total !== 1 ? "s" : ""}
          </span>
          <select
            className={`input ${styles.sortSelect}`}
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
          >
            <option value="relevance">Sort: relevance</option>
            <option value="date">Sort: date</option>
            <option value="site">Sort: findspot</option>
            <option value="id">Sort: ID</option>
          </select>
        </div>
      </div>

      <div className={styles.layout}>
        {/* Facet sidebar */}
        <aside className={styles.facets}>
          <h3 className={styles.facetTitle}>Classification</h3>
          {activeClass && (
            <button
              className={styles.clearFilter}
              onClick={() => setActiveClass(null)}
            >
              Clear filter
            </button>
          )}
          <ul className={styles.facetList}>
            {facets.map(({ cls, count }) => (
              <li key={cls}>
                <button
                  className={`${styles.facetBtn} ${activeClass === cls ? styles.facetActive : ""}`}
                  onClick={() => setActiveClass(activeClass === cls ? null : cls)}
                >
                  <span
                    className={styles.facetDot}
                    style={{ background: CLASS_COLORS[cls] || CLASS_COLORS.unknown }}
                  />
                  <span className={styles.facetLabel}>{cls}</span>
                  <span className={styles.facetCount}>{count}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* Results */}
        <div className={styles.results}>
          {sorted.map((insc) => {
            const cls = insc.classification || "unknown";
            const color = CLASS_COLORS[cls] || CLASS_COLORS.unknown;
            return (
              <Link
                key={insc.id}
                href={`/inscription/${encodeURIComponent(insc.id)}`}
                className={`card ${styles.resultCard}`}
              >
                <div className={styles.resultHeader}>
                  <span className={styles.resultId}>{insc.id}</span>
                  <span
                    className={styles.resultBadge}
                    style={{ color, borderColor: color }}
                  >
                    {cls}
                  </span>
                </div>
                <p className={styles.resultOldItalic}>
                  {insc.old_italic || toOldItalic(insc.canonical)}
                </p>
                <p className={styles.resultCanonical}>{insc.canonical}</p>
                <div className={styles.resultMeta}>
                  {insc.findspot && <span>{insc.findspot}</span>}
                  <span>{dateDisplay(insc)}</span>
                </div>
              </Link>
            );
          })}

          {results.length < total && (
            <button
              className="btn btn-secondary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={handleLoadMore}
              disabled={loading}
            >
              {loading ? "Loading..." : `Load more (${total - results.length} remaining)`}
            </button>
          )}

          {!loading && results.length === 0 && (
            <p className={styles.noResults}>
              No inscriptions match the current query and filters.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
