"use client";

import { useEffect, useState } from "react";
import type { StatsSummary } from "@/lib/corpus";
import { fetchStatsSummary, CLASS_COLORS } from "@/lib/corpus";

export default function StatsPage() {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  useEffect(() => {
    fetchStatsSummary().then(setStats).catch(console.error);
  }, []);

  if (!stats) {
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
          { label: "Total Inscriptions", value: stats.total.toLocaleString() },
          { label: "With Coordinates", value: stats.with_coords.toLocaleString() },
          { label: "Pleiades Links", value: stats.pleiades_linked.toLocaleString() },
          { label: "Classified", value: stats.classified.toLocaleString() },
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
          {stats.classification_counts.map(([cls, count]) => {
            const pct = (count / stats.total) * 100;
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
          {stats.top_sites.map(([site, count]) => {
            const pct = (count / stats.total) * 100;
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
