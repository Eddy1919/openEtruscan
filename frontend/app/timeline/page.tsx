"use client";

import { useEffect, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import type { TimelineItem } from "@/lib/corpus";
import { fetchTimeline } from "@/lib/corpus";
import styles from "./page.module.css";

const MapContainer = dynamic(
  () => import("react-leaflet").then((mod) => mod.MapContainer),
  { ssr: false }
);
const TileLayer = dynamic(
  () => import("react-leaflet").then((mod) => mod.TileLayer),
  { ssr: false }
);
const CircleMarker = dynamic(
  () => import("react-leaflet").then((mod) => mod.CircleMarker),
  { ssr: false }
);
const Tooltip = dynamic(
  () => import("react-leaflet").then((mod) => mod.Tooltip),
  { ssr: false }
);

const PERIODS = [
  { label: "Pre-700 BCE", min: -1000, max: -700, color: "#c084fc" },
  { label: "700-500 BCE", min: -700, max: -500, color: "#6395f2" },
  { label: "500-300 BCE", min: -500, max: -300, color: "#4ade80" },
  { label: "300-100 BCE", min: -300, max: -100, color: "#fbbf24" },
  { label: "Post-100 BCE", min: -100, max: 500, color: "#f87171" },
];

function getPeriodColor(dateApprox: number): string {
  for (const p of PERIODS) {
    if (dateApprox >= p.min && dateApprox < p.max) return p.color;
  }
  return "#6b6962";
}

export default function TimelinePage() {
  const [dated, setDated] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<[number, number]>([-800, -100]);

  useEffect(() => {
    fetchTimeline()
      .then((res) => setDated(res.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return dated.filter(
      (i) => i.date_approx >= range[0] && i.date_approx <= range[1]
    );
  }, [dated, range]);

  // Group by location for clustering
  const clusters = useMemo(() => {
    const map = new Map<string, { lat: number; lon: number; name: string; count: number; items: TimelineItem[] }>();
    filtered.forEach((i) => {
      const key = `${i.findspot_lat.toFixed(2)}_${i.findspot_lon.toFixed(2)}`;
      if (!map.has(key)) {
        map.set(key, { lat: i.findspot_lat, lon: i.findspot_lon, name: i.findspot || "Unknown", count: 0, items: [] });
      }
      const cluster = map.get(key)!;
      cluster.count++;
      cluster.items.push(i);
    });
    return Array.from(map.values());
  }, [filtered]);

  const periodCounts = useMemo(() => {
    return PERIODS.map((p) => ({
      ...p,
      count: filtered.filter(
        (i) => i.date_approx >= p.min && i.date_approx < p.max
      ).length,
    }));
  }, [filtered]);

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 400 }} />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>
      <h1 className={styles.heading}>Timeline</h1>
      <p className={styles.subtitle}>
        Temporal distribution of {dated.length.toLocaleString()} dated
        inscriptions. Drag the range slider to filter by century.
      </p>

      {/* Range controls */}
      <div className={styles.controls}>
        <div className={styles.rangeGroup}>
          <label className={styles.rangeLabel}>
            From: {Math.abs(range[0])} BCE
          </label>
          <input
            type="range"
            min={-800}
            max={0}
            value={range[0]}
            onChange={(e) =>
              setRange([Math.min(Number(e.target.value), range[1] - 50), range[1]])
            }
            className={styles.rangeSlider}
          />
        </div>
        <div className={styles.rangeGroup}>
          <label className={styles.rangeLabel}>
            To: {Math.abs(range[1])} BCE
          </label>
          <input
            type="range"
            min={-800}
            max={0}
            value={range[1]}
            onChange={(e) =>
              setRange([range[0], Math.max(Number(e.target.value), range[0] + 50)])
            }
            className={styles.rangeSlider}
          />
        </div>
        <span className={styles.filterCount}>
          {filtered.length.toLocaleString()} inscriptions in range
        </span>
      </div>

      {/* Period legend */}
      <div className={styles.legend}>
        {periodCounts.map((p) => (
          <div key={p.label} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: p.color }} />
            <span className={styles.legendLabel}>{p.label}</span>
            <span className={styles.legendCount}>{p.count}</span>
          </div>
        ))}
      </div>

      {/* Map */}
      <div className={styles.mapWrap}>
        <MapContainer
          center={[42.8, 12.0]}
          zoom={6}
          style={{ height: "100%", width: "100%" }}
          scrollWheelZoom={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          />
          {clusters.map((c) => (
            <CircleMarker
              key={`${c.lat}_${c.lon}`}
              center={[c.lat, c.lon]}
              radius={Math.min(4 + Math.sqrt(c.count) * 3, 20)}
              pathOptions={{
                fillColor: c.items[0]?.date_approx != null
                  ? getPeriodColor(c.items[0].date_approx)
                  : "#6b6962",
                fillOpacity: 0.8,
                color: "rgba(255,255,255,0.3)",
                weight: 1,
              }}
            >
              <Tooltip>
                <strong>{c.name}</strong>
                <br />
                {c.count} inscription{c.count !== 1 ? "s" : ""} in range
              </Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
