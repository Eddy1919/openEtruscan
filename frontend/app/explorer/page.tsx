"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import type { Inscription, StatsSummary } from "@/lib/corpus";
import { searchCorpus, fetchStatsSummary, dateDisplay, CLASS_COLORS, toOldItalic } from "@/lib/corpus";
import styles from "./page.module.css";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function ExplorerPage() {
  const [results, setResults] = useState<Inscription[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [selected, setSelected] = useState<Inscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch filter options once
  useEffect(() => {
    fetchStatsSummary().then(setStats).catch(console.error);
  }, []);

  const doSearch = useCallback(
    (text: string, findspot: string, classification: string) => {
      setLoading(true);
      searchCorpus({
        text: text || undefined,
        findspot: findspot || undefined,
        classification: classification || undefined,
        limit: 500,
      })
        .then((res) => {
          setResults(res.results);
          setTotal(res.total);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    },
    []
  );

  // Initial load
  useEffect(() => {
    doSearch("", "", "");
  }, [doSearch]);

  // Debounced search on filter change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query, siteFilter, classFilter);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, siteFilter, classFilter, doSearch]);

  const geoFiltered = useMemo(
    () => results.filter((i) => i.findspot_lat != null && i.findspot_lon != null),
    [results]
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
                {(stats?.distinct_sites || []).map((s) => (
                  <option key={s} value={s}>{s}</option>
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
                {(stats?.distinct_classifications || []).map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div className={styles.resultCount}>
            {loading ? "Searching..." : `${total.toLocaleString()} inscriptions`}
          </div>
        </div>

        {/* Results list */}
        <div className={styles.resultList}>
          {results.slice(0, 200).map((insc) => (
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
              <div className="inscription-text">{insc.old_italic || toOldItalic(insc.canonical)}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '0.2rem' }}>{insc.canonical}</div>
              <div className={styles.resultMeta}>
                {insc.findspot && <span>{insc.findspot}</span>}
                <span>{dateDisplay(insc)}</span>
              </div>
            </div>
          ))}
          {results.length > 200 && (
            <div className={styles.moreIndicator}>
              + {(results.length - 200).toLocaleString()} more…
            </div>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="split-main">
        {results.length > 0 && (
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
