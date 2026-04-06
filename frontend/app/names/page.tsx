"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import type { NameNode, NameEdge } from "@/lib/corpus";
import { fetchNamesNetwork, fetchStatsSummary } from "@/lib/corpus";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineSplitPane } from "@/components/aldine/SplitPane";
import { AldineEntity } from "@/components/aldine/Entity";

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

  // Force-directed layout on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;

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
    const maxFrames = 300;

    function simulate() {
      if (frame >= maxFrames || !ctx) return;

      // Repulsion
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = positions[nodes[i].id];
          const b = positions[nodes[j].id];
          if (!a || !b) continue;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = 3000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      // Attraction
      for (const edge of edges) {
        const a = positions[edge.source];
        const b = positions[edge.target];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const force = (dist - 120) * 0.015 * edge.weight;
        const fx = (dx / Math.max(dist, 1)) * force;
        const fy = (dy / Math.max(dist, 1)) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Gravity
      for (const n of nodes) {
        const p = positions[n.id];
        if (!p) continue;
        p.vx += (cx - p.x) * 0.002;
        p.vy += (cy - p.y) * 0.002;
      }

      const damping = 0.8;
      for (const n of nodes) {
        const p = positions[n.id];
        if (!p) continue;
        p.vx *= damping;
        p.vy *= damping;
        p.x += p.vx;
        p.y += p.vy;
        p.x = Math.max(50, Math.min(W - 50, p.x));
        p.y = Math.max(50, Math.min(H - 50, p.y));
      }

      ctx.clearRect(0, 0, W, H);

      // Edges (Aldine Ink)
      ctx.strokeStyle = "rgba(43, 33, 30, 0.08)"; 
      for (const edge of edges) {
        const a = positions[edge.source];
        const b = positions[edge.target];
        if (!a || !b) continue;
        ctx.lineWidth = Math.min(edge.weight * 0.5, 1.5);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      // Nodes (Aldine Terracotta scaling)
      const maxC = Math.max(...nodes.map((n) => n.count), 1);
      for (const n of nodes) {
        const p = positions[n.id];
        if (!p) continue;
        const radius = 5 + (n.count / maxC) * 18;
        
        ctx.fillStyle = `rgba(162, 87, 75, ${0.3 + (n.count / maxC) * 0.7})`; 
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();

        // Label
        ctx.fillStyle = "rgba(43, 33, 30, 0.9)"; 
        ctx.font = `${Math.max(10, 10 + (n.count / maxC) * 4)}px "EB Garamond", serif`;
        ctx.textAlign = "center";
        ctx.globalAlpha = 1.0;
        ctx.fillText(n.id, p.x, p.y - radius - 6);
      }

      frame++;
      requestAnimationFrame(simulate);
    }

    const rafId = requestAnimationFrame(simulate);
    return () => cancelAnimationFrame(rafId);
  }, [nodes, edges]);

  const topNodes = useMemo(() => nodes.slice(0, 30), [nodes]);

  const NetworkPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-hidden aldine-relative aldine-bg-bone">
        {loading && (
          <Box className="aldine-absolute aldine-inset-0 aldine-z-50 aldine-flex aldine-center aldine-bg-canvas aldine-opacity-50 aldine-backdrop-blur-sm">
             <span className="aldine-text-xs aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-ink-muted aldine-animate-pulse">Synthesizing Topological Vertices</span>
          </Box>
        )}

        <Box className="aldine-absolute aldine-top-8 aldine-left-8 aldine-z-10 aldine-w-[300px] aldine-animate-in aldine-stagger-1">
           <Box surface="canvas" border="all" padding={6} className="aldine-border-hairline aldine-shadow-sm aldine-backdrop-blur-md aldine-opacity-95">
              <Ornament.Label className="aldine-accent aldine-mb-2">Network Control</Ornament.Label>
              <h2 className="aldine-text-2xl aldine-font-display aldine-ink-base aldine-italic aldine-mb-4">Prosopography</h2>
              <Stack gap={2}>
                 <Row justify="between">
                    <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest aldine-ink-muted">Min Attestations</span>
                    <span className="aldine-text-xs aldine-font-mono aldine-ink-base">{minCount}</span>
                 </Row>
                 <input 
                    type="range" 
                    min="2" 
                    max="50" 
                    step="1" 
                    value={minCount}
                    onChange={(e) => setMinCount(parseInt(e.target.value))}
                    className="aldine-w-full aldine-h-px aldine-bg-ink-muted aldine-opacity-20 aldine-appearance-none aldine-rounded-none aldine-cursor-pointer aldine-accent-terracotta" 
                 />
                 <p className="aldine-text-[9px] aldine-font-editorial aldine-ink-muted aldine-leading-relaxed aldine-mt-4 aldine-italic">
                    Relational neural mapping of nominal references extracted from {totalInscriptions.toLocaleString()} texts.
                 </p>
              </Stack>
           </Box>
        </Box>

        <canvas
           ref={canvasRef}
           width={1400}
           height={1000}
           className="aldine-w-full aldine-h-full aldine-cursor-crosshair aldine-transition-opacity aldine-duration-1000"
           style={{ opacity: loading ? 0 : 1 }}
        />

        <Box className="aldine-absolute aldine-bottom-8 aldine-right-8 aldine-opacity-40">
           <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-[0.3em] aldine-accent aldine-font-mono">Neural Force Distribution</span>
        </Box>
     </Box>
  );

  const StatsPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-y-auto aldine-px-8 aldine-py-16 aldine-bg-canvas">
        <Box border="bottom" padding={4} className="aldine-mb-12 aldine-animate-in aldine-stagger-1">
           <Ornament.Label className="aldine-accent">Hierarchical Index</Ornament.Label>
           <h3 className="aldine-text-2xl aldine-font-display aldine-italic aldine-ink-base">Entity Frequency Matrix</h3>
        </Box>

        <Stack gap={6} className="aldine-animate-in aldine-stagger-2">
           {topNodes.map((n, i) => {
             const pct = (n.count / (nodes[0]?.count || 1)) * 100;
             return (
               <Stack key={n.id} gap={1} className="aldine-group">
                  <Row justify="between" align="end">
                     <Row gap={3} align="center">
                        <span className="aldine-text-[9px] aldine-font-mono aldine-ink-muted aldine-opacity-30 aldine-w-4 aldine-block">#{i+1}</span>
                        <AldineEntity type="unknown">
                           <span className="group-hover:aldine-accent aldine-transition-colors">{n.id}</span>
                        </AldineEntity>
                     </Row>
                     <span className="aldine-text-xs aldine-font-mono aldine-font-bold aldine-ink-muted">{n.count}</span>
                  </Row>
                  <Box className="aldine-w-full aldine-h-line aldine-bg-bone/40 aldine-relative aldine-overflow-hidden aldine-ml-7">
                     <div className="aldine-absolute aldine-top-0 aldine-left-0 aldine-h-full aldine-transition-all aldine-duration-1000" style={{ width: `${pct}%`, backgroundColor: 'var(--aldine-terracotta)', opacity: 0.7 }} />
                  </Box>
               </Stack>
             );
           })}
           
           {topNodes.length === 0 && !loading && (
              <Box className="aldine-py-12 aldine-flex aldine-center aldine-text-[10px] aldine-font-mono aldine-uppercase aldine-tracking-widest aldine-ink-muted aldine-opacity-50">
                 Index Empty
              </Box>
           )}
        </Stack>
     </Box>
  );

  return (
     <Box className="aldine-grow aldine-flex aldine-col aldine-h-content">
        <AldineSplitPane 
          leftPane={NetworkPane} 
          rightPane={StatsPane} 
          initialRatio={61.8}
        />
     </Box>
  );
}






