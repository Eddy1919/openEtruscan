"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import type { Inscription } from "@/lib/corpus";
import { loadCorpus, dateDisplay, CLASS_COLORS } from "@/lib/corpus";
import styles from "./page.module.css";

// Lazy-load the map to avoid SSR issues with WebGL
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function ExplorerPage() {
  const [corpus, setCorpus] = useState<Inscription[]>([]);
  const [query, setQuery] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [selected, setSelected] = useState<Inscription | null>(null);

  useEffect(() => {
    loadCorpus().then(setCorpus);
  }, []);

  const sites = useMemo(() => {
    const s = new Set(corpus.map((i) => i.findspot).filter(Boolean));
    return Array.from(s).sort() as string[];
  }, [corpus]);

  const classifications = useMemo(() => {
    const c = new Set(corpus.map((i) => i.classification).filter(Boolean));
    return Array.from(c).sort() as string[];
  }, [corpus]);

  const filtered = useMemo(() => {
    let results = corpus;
    if (query) {
      const q = query.toLowerCase();
      results = results.filter(
        (i) =>
          i.canonical?.toLowerCase().includes(q) ||
          i.id.toLowerCase().includes(q)
      );
    }
    if (siteFilter) {
      results = results.filter((i) => i.findspot === siteFilter);
    }
    if (classFilter) {
      results = results.filter((i) => i.classification === classFilter);
    }
    return results;
  }, [corpus, query, siteFilter, classFilter]);

  const geoFiltered = useMemo(
    () => filtered.filter((i) => i.findspot_lat != null && i.findspot_lon != null),
    [filtered]
  );

  const handleMapClick = useCallback(
    (info: { object?: Inscription }) => {
      if (info.object) setSelected(info.object);
    },
    []
  );

  return (
    <div className="split-layout">
      {/* Sidebar */}
      <div className="split-sidebar">
        <div className={styles.searchForm}>
          <div className={styles.formGroup}>
            <label>Search text or ID</label>
            <input
              className="input"
              placeholder="e.g. laris or ETP_001"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label>Find site</label>
              <select
                className="input"
                value={siteFilter}
                onChange={(e) => setSiteFilter(e.target.value)}
              >
                <option value="">All sites</option>
                {sites.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Type</label>
              <select
                className="input"
                value={classFilter}
                onChange={(e) => setClassFilter(e.target.value)}
              >
                <option value="">All types</option>
                {classifications.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className={styles.resultCount}>
            {filtered.length.toLocaleString()} inscriptions
          </div>
        </div>

        {/* Results list */}
        <div className={styles.resultList}>
          {filtered.slice(0, 200).map((insc) => (
            <div
              key={insc.id}
              className={`${styles.resultCard} ${
                selected?.id === insc.id ? styles.selected : ""
              }`}
              onClick={() => setSelected(insc)}
            >
              <div className={styles.resultHeader}>
                <Link
                  href={`/inscription/${encodeURIComponent(insc.id)}`}
                  className={styles.resultId}
                >
                  {insc.id}
                </Link>
                {insc.classification && insc.classification !== "unknown" && (
                  <span
                    className="badge badge-accent"
                    style={{
                      borderColor:
                        CLASS_COLORS[insc.classification] || CLASS_COLORS.unknown,
                      color:
                        CLASS_COLORS[insc.classification] || CLASS_COLORS.unknown,
                    }}
                  >
                    {insc.classification}
                  </span>
                )}
              </div>
              <div className="inscription-text">{insc.canonical}</div>
              <div className={styles.resultMeta}>
                {insc.findspot && <span>📍 {insc.findspot}</span>}
                <span>{dateDisplay(insc)}</span>
              </div>
            </div>
          ))}
          {filtered.length > 200 && (
            <div className={styles.moreIndicator}>
              + {(filtered.length - 200).toLocaleString()} more…
            </div>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="split-main">
        {corpus.length > 0 && (
          <MapView
            inscriptions={geoFiltered}
            selected={selected}
            onInscriptionClick={handleMapClick}
          />
        )}
      </div>
    </div>
  );
}
