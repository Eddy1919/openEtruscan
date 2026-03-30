"use client";

import { useEffect, useState, useRef } from "react";
import type { NameNode, NameEdge } from "@/lib/corpus";
import { fetchNamesNetwork, fetchStatsSummary } from "@/lib/corpus";
import styles from "./page.module.css";

export default function NamesPage() {
  const [nodes, setNodes] = useState<NameNode[]>([]);
  const [edges, setEdges] = useState<NameEdge[]>([]);
  const [minCount, setMinCount] = useState(5);
  const [loading, setLoading] = useState(true);
  const [totalInscriptions, setTotalInscriptions] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    fetchStatsSummary()
      .then((s) => setTotalInscriptions(s.total))
      .catch(console.error);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchNamesNetwork(minCount)
      .then((res) => {
        setNodes(res.nodes);
        setEdges(res.edges);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [minCount]);

  // Simple force-directed layout on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;

    // Initialize random positions
    const positions: Record<string, { x: number; y: number; vx: number; vy: number }> = {};
    nodes.forEach((n) => {
      positions[n.id] = {
        x: cx + (Math.random() - 0.5) * W * 0.6,
        y: cy + (Math.random() - 0.5) * H * 0.6,
        vx: 0,
        vy: 0,
      };
    });

    let frame = 0;
    const maxFrames = 200;

    function simulate() {
      if (frame >= maxFrames || !ctx) return;

      // Repulsion (all pairs)
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = positions[nodes[i].id];
          const b = positions[nodes[j].id];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = 2000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      // Attraction (edges)
      for (const edge of edges) {
        const a = positions[edge.source];
        const b = positions[edge.target];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const force = (dist - 100) * 0.01 * edge.weight;
        const fx = (dx / Math.max(dist, 1)) * force;
        const fy = (dy / Math.max(dist, 1)) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Gravity toward centre
      for (const n of nodes) {
        const p = positions[n.id];
        p.vx += (cx - p.x) * 0.001;
        p.vy += (cy - p.y) * 0.001;
      }

      // Apply velocity with damping
      const damping = 0.85;
      for (const n of nodes) {
        const p = positions[n.id];
        p.vx *= damping;
        p.vy *= damping;
        p.x += p.vx;
        p.y += p.vy;
        p.x = Math.max(30, Math.min(W - 30, p.x));
        p.y = Math.max(30, Math.min(H - 30, p.y));
      }

      // Draw
      ctx.clearRect(0, 0, W, H);

      // Edges
      ctx.strokeStyle = "rgba(196, 112, 75, 0.2)";
      for (const edge of edges) {
        const a = positions[edge.source];
        const b = positions[edge.target];
        if (!a || !b) continue;
        ctx.lineWidth = Math.min(edge.weight * 0.5, 3);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // Nodes
      const maxCount = Math.max(...nodes.map((n) => n.count), 1);
      for (const n of nodes) {
        const p = positions[n.id];
        const radius = 4 + (n.count / maxCount) * 16;
        ctx.fillStyle = `rgba(196, 112, 75, ${0.4 + (n.count / maxCount) * 0.6})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();

        // Label
        ctx.fillStyle = "#e8e6e3";
        ctx.font = `${Math.max(10, 10 + (n.count / maxCount) * 4)}px "JetBrains Mono", monospace`;
        ctx.textAlign = "center";
        ctx.fillText(n.id, p.x, p.y - radius - 4);
      }

      frame++;
      requestAnimationFrame(simulate);
    }

    simulate();
  }, [nodes, edges]);

  if (loading && nodes.length === 0) {
    return (
      <div className="page-container">
        <div className="loading-shimmer" style={{ height: 400 }} />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>
      <h1 className={styles.heading}>Prosopography</h1>
      <p className={styles.subtitle}>
        Network of personal names extracted from {totalInscriptions.toLocaleString()} inscriptions.
        Nodes are sized by frequency; edges connect names co-occurring in the
        same inscription text.
      </p>

      <div className={styles.controls}>
        <label className={styles.controlLabel}>
          Minimum attestations:
          <input
            type="range"
            min={2}
            max={30}
            value={minCount}
            onChange={(e) => setMinCount(Number(e.target.value))}
            className={styles.rangeSlider}
          />
          <span className={styles.controlValue}>{minCount}</span>
        </label>
        <span className={styles.stats}>
          {nodes.length} names, {edges.length} co-occurrences
        </span>
      </div>

      <div className={styles.canvasWrap}>
        <canvas
          ref={canvasRef}
          width={1100}
          height={600}
          className={styles.canvas}
        />
      </div>

      {/* Name frequency table */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3 className={styles.tableTitle}>Name Frequency</h3>
        <div className={styles.nameGrid}>
          {nodes.slice(0, 30).map((n) => (
            <div key={n.id} className={styles.nameRow}>
              <span className={styles.nameText}>{n.id}</span>
              <span className={styles.nameCount}>{n.count}</span>
              <div className={styles.nameBar}>
                <div
                  className={styles.nameBarFill}
                  style={{
                    width: `${(n.count / (nodes[0]?.count || 1)) * 100}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
