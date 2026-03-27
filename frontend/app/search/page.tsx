"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import type { Inscription } from "@/lib/corpus";
import { loadCorpus, toOldItalic, dateDisplay, CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";

const CLASSIFICATIONS = [
  "funerary", "votive", "dedicatory", "legal",
  "commercial", "boundary", "ownership", "unknown",
];

const PAGE_SIZE = 50;

type SortKey = "relevance" | "date" | "site" | "id";

export default function SearchPage() {
  const [corpus, setCorpus] = useState<Inscription[]>([]);
  const [query, setQuery] = useState("");
  const [activeClass, setActiveClass] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortKey>("relevance");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    loadCorpus().then(setCorpus);
  }, []);

  const queryLower = query.toLowerCase().trim();

  const filtered = useMemo(() => {
    if (!queryLower && !activeClass) return corpus;
    return corpus.filter((insc) => {
      if (activeClass) {
        const cls = insc.classification || "unknown";
        if (cls !== activeClass) return false;
      }
      if (!queryLower) return true;
      return (
        insc.canonical.toLowerCase().includes(queryLower) ||
        insc.id.toLowerCase().includes(queryLower) ||
        (insc.findspot || "").toLowerCase().includes(queryLower) ||
        (insc.old_italic || "").includes(queryLower)
      );
    });
  }, [corpus, queryLower, activeClass]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    switch (sortBy) {
      case "date":
        return arr.sort((a, b) => (a.date_approx ?? 9999) - (b.date_approx ?? 9999));
      case "site":
        return arr.sort((a, b) => (a.findspot || "").localeCompare(b.findspot || ""));
      case "id":
        return arr.sort((a, b) => a.id.localeCompare(b.id));
      default:
        return arr;
    }
  }, [filtered, sortBy]);

  const facets = useMemo(() => {
    const map = new Map<string, number>();
    filtered.forEach((insc) => {
      const cls = insc.classification || "unknown";
      map.set(cls, (map.get(cls) || 0) + 1);
    });
    return CLASSIFICATIONS
      .map((cls) => ({ cls, count: map.get(cls) || 0 }))
      .filter((f) => f.count > 0);
  }, [filtered]);

  const visible = sorted.slice(0, visibleCount);

  if (!corpus.length) {
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
        Query {corpus.length.toLocaleString()} inscriptions by text, identifier,
        findspot, or Old Italic Unicode.
      </p>

      {/* Search input */}
      <div className={styles.searchBar}>
        <input
          type="text"
          className={`input ${styles.searchInput}`}
          placeholder="e.g. laris, turce, Volsinii, Cr 2.20"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setVisibleCount(PAGE_SIZE);
          }}
        />
        <div className={styles.sortRow}>
          <span className={styles.resultCount}>
            {filtered.length.toLocaleString()} result{filtered.length !== 1 ? "s" : ""}
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
              onClick={() => { setActiveClass(null); setVisibleCount(PAGE_SIZE); }}
            >
              Clear filter
            </button>
          )}
          <ul className={styles.facetList}>
            {facets.map(({ cls, count }) => (
              <li key={cls}>
                <button
                  className={`${styles.facetBtn} ${activeClass === cls ? styles.facetActive : ""}`}
                  onClick={() => {
                    setActiveClass(activeClass === cls ? null : cls);
                    setVisibleCount(PAGE_SIZE);
                  }}
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
          {visible.map((insc) => {
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

          {visibleCount < sorted.length && (
            <button
              className="btn btn-secondary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
            >
              Load more ({sorted.length - visibleCount} remaining)
            </button>
          )}

          {filtered.length === 0 && (
            <p className={styles.noResults}>
              No inscriptions match the current query and filters.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
