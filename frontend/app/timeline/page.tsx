"use client";

import { useEffect, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import type { TimelineItem } from "@/lib/corpus";
import { fetchTimeline } from "@/lib/corpus";
import styles from "./page.module.css";
import MapboxMap, { Source, Layer, Popup } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";
import type { MapLayerMouseEvent } from "react-map-gl/mapbox";
import type { CircleLayer } from "react-map-gl/mapbox";






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
  const [hoverInfo, setHoverInfo] = useState<any>(null);

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
        <MapboxMap
          initialViewState={{ longitude: 12.0, latitude: 42.8, zoom: 6 }}
          mapStyle="mapbox://styles/mapbox/dark-v11"
          mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
          interactiveLayerIds={["timeline-circles"]}
          onMouseMove={(e) => {
            if (e.features && e.features.length > 0) {
              setHoverInfo({
                feature: e.features[0],
                x: e.point.x,
                y: e.point.y
              });
            } else {
              setHoverInfo(null);
            }
          }}
          onMouseLeave={() => setHoverInfo(null)}
        >
          <Source
            id="timeline-clusters"
            type="geojson"
            data={{
              type: "FeatureCollection",
              features: clusters.map((c) => ({
                type: "Feature",
                geometry: { type: "Point", coordinates: [c.lon, c.lat] },
                properties: {
                  name: c.name,
                  count: c.count,
                  color: c.items[0]?.date_approx != null ? getPeriodColor(c.items[0].date_approx) : "#6b6962",
                  radius: Math.min(4 + Math.sqrt(c.count) * 3, 20)
                }
              }))
            }}
          >
            <Layer
              id="timeline-circles"
              type="circle"
              paint={{
                "circle-radius": ["get", "radius"],
                "circle-color": ["get", "color"],
                "circle-opacity": 0.8,
                "circle-stroke-width": 1,
                "circle-stroke-color": "rgba(255,255,255,0.3)"
              }}
            />
          </Source>
          
          {hoverInfo && (
            <div
              style={{
                position: "absolute",
                left: hoverInfo.x,
                top: hoverInfo.y,
                background: "rgba(0,0,0,0.8)",
                color: "white",
                padding: "4px 8px",
                borderRadius: "4px",
                pointerEvents: "none",
                transform: "translate(-50%, -100%)",
                marginTop: "-10px",
                fontSize: "12px",
                zIndex: 10
              }}
            >
              <strong>{hoverInfo.feature.properties.name}</strong><br/>
              {hoverInfo.feature.properties.count} inscription{hoverInfo.feature.properties.count !== 1 ? "s" : ""} in range
            </div>
          )}
        </MapboxMap>
      </div>
    </div>
  );
}
