"use client";

import { useEffect, useState, useMemo } from "react";
import type { Inscription } from "@/lib/corpus";
import { loadCorpus, CLASS_COLORS } from "@/lib/corpus";

export default function StatsPage() {
  const [corpus, setCorpus] = useState<Inscription[]>([]);
  useEffect(() => {
    loadCorpus().then(setCorpus);
  }, []);

  const siteCounts = useMemo(() => {
    const map = new Map<string, number>();
    corpus.forEach((i) => {
      const site = i.findspot || "Unknown";
      map.set(site, (map.get(site) || 0) + 1);
    });
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20);
  }, [corpus]);

  const classCounts = useMemo(() => {
    const map = new Map<string, number>();
    corpus.forEach((i) => {
      const cls = i.classification || "unknown";
      map.set(cls, (map.get(cls) || 0) + 1);
    });
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [corpus]);

  const textLengths = useMemo(() => {
    const buckets = new Map<string, number>();
    corpus.forEach((i) => {
      const len = i.canonical.length;
      const bucket =
        len <= 5
          ? "1-5"
          : len <= 10
            ? "6-10"
            : len <= 20
              ? "11-20"
              : len <= 50
                ? "21-50"
                : "50+";
      buckets.set(bucket, (buckets.get(bucket) || 0) + 1);
    });
    return Array.from(buckets.entries());
  }, [corpus]);

  if (!corpus.length) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 200 }} />
      </div>
    );
  }

  return (
    <div className="page-container">
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "2rem",
          marginBottom: "2rem",
        }}
      >
        Corpus Statistics
      </h1>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "1rem",
          marginBottom: "2rem",
        }}
      >
        {[
          { label: "Total Inscriptions", value: corpus.length.toLocaleString() },
          {
            label: "With Coordinates",
            value: corpus
              .filter((i) => i.findspot_lat != null)
              .length.toLocaleString(),
          },
          {
            label: "Pleiades Links",
            value: corpus
              .filter((i) => i.pleiades_id)
              .length.toLocaleString(),
          },
          {
            label: "Classified",
            value: corpus
              .filter(
                (i) => i.classification && i.classification !== "unknown"
              )
              .length.toLocaleString(),
          },
        ].map((s) => (
          <div className="card" key={s.label} style={{ textAlign: "center" }}>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "1.8rem",
                color: "var(--accent)",
              }}
            >
              {s.value}
            </div>
            <div
              style={{
                fontSize: "0.75rem",
                color: "var(--text-muted)",
                textTransform: "uppercase",
              }}
            >
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Classification distribution */}
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h2
          style={{
            fontSize: "1rem",
            marginBottom: "1rem",
            color: "var(--text-secondary)",
          }}
        >
          Classification Distribution
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {classCounts.map(([cls, count]) => {
            const pct = (count / corpus.length) * 100;
            const color = CLASS_COLORS[cls] || CLASS_COLORS.unknown;
            return (
              <div
                key={cls}
                style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}
              >
                <span
                  style={{
                    width: 100,
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                    textAlign: "right",
                  }}
                >
                  {cls}
                </span>
                <div
                  style={{
                    flex: 1,
                    height: 20,
                    background: "var(--bg-primary)",
                    borderRadius: 4,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${pct}%`,
                      height: "100%",
                      background: color,
                      borderRadius: 4,
                      transition: "width 0.5s ease",
                    }}
                  />
                </div>
                <span
                  style={{
                    width: 60,
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                  }}
                >
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Top sites */}
      <div className="card">
        <h2
          style={{
            fontSize: "1rem",
            marginBottom: "1rem",
            color: "var(--text-secondary)",
          }}
        >
          Top Find Sites
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {siteCounts.map(([site, count]) => {
            const pct = (count / corpus.length) * 100;
            return (
              <div
                key={site}
                style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}
              >
                <span
                  style={{
                    width: 160,
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                    textAlign: "right",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {site}
                </span>
                <div
                  style={{
                    flex: 1,
                    height: 16,
                    background: "var(--bg-primary)",
                    borderRadius: 4,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${pct}%`,
                      height: "100%",
                      background: "var(--accent)",
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span
                  style={{
                    width: 40,
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                  }}
                >
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
