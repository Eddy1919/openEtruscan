"use client";

import { useEffect, useRef } from "react";

const GLYPHS = "𐌀𐌁𐌂𐌃𐌄𐌅𐌆𐌇𐌈𐌉𐌊𐌋𐌌𐌍𐌎𐌏𐌐𐌑𐌓𐌔𐌕𐌖𐌗𐌘𐌙𐌚";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  glyph: string;
  size: number;
  opacity: number;
  targetOpacity: number;
  rotation: number;
  rotationSpeed: number;
  life: number;
  maxLife: number;
}

export default function GlyphField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particles = useRef<Particle[]>([]);
  const mouse = useRef({ x: -1000, y: -1000 });
  const animationId = useRef<number>(0);
  const dims = useRef({ w: 0, h: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = parent.getBoundingClientRect();
      dims.current = { w: rect.width, h: rect.height };
      canvas!.width = rect.width * dpr;
      canvas!.height = rect.height * dpr;
      canvas!.style.width = `${rect.width}px`;
      canvas!.style.height = `${rect.height}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    window.addEventListener("resize", resize);

    function spawnParticle(): Particle {
      const { w, h } = dims.current;
      const glyphArr = [...GLYPHS];
      return {
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3,
        vy: -0.15 - Math.random() * 0.25,
        glyph: glyphArr[Math.floor(Math.random() * glyphArr.length)],
        size: 12 + Math.random() * 20,
        opacity: 0,
        targetOpacity: 0.06 + Math.random() * 0.14,
        rotation: Math.random() * Math.PI * 2,
        rotationSpeed: (Math.random() - 0.5) * 0.003,
        life: 0,
        maxLife: 600 + Math.random() * 800,
      };
    }

    // Seed
    const count = Math.floor((dims.current.w * dims.current.h) / 12000);
    for (let i = 0; i < count; i++) {
      const p = spawnParticle();
      p.life = Math.random() * p.maxLife;
      p.opacity = p.targetOpacity;
      particles.current.push(p);
    }

    function handleMouse(e: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      mouse.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    function handleLeave() {
      mouse.current = { x: -1000, y: -1000 };
    }

    canvas!.addEventListener("mousemove", handleMouse);
    canvas!.addEventListener("mouseleave", handleLeave);

    function draw() {
      if (!ctx) return;
      const { w, h } = dims.current;
      ctx.clearRect(0, 0, w, h);

      const mx = mouse.current.x;
      const my = mouse.current.y;

      for (let i = particles.current.length - 1; i >= 0; i--) {
        const p = particles.current[i];
        p.life++;
        p.x += p.vx;
        p.y += p.vy;
        p.rotation += p.rotationSpeed;

        // Fade in first 60 frames, fade out last 120
        if (p.life < 60) {
          p.opacity = p.targetOpacity * (p.life / 60);
        } else if (p.life > p.maxLife - 120) {
          p.opacity = p.targetOpacity * ((p.maxLife - p.life) / 120);
        } else {
          p.opacity = p.targetOpacity;
        }

        // Mouse attraction — glyphs brighten and drift toward cursor
        const dx = mx - p.x;
        const dy = my - p.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 200) {
          const pull = (1 - dist / 200) * 0.02;
          p.vx += dx * pull * 0.01;
          p.vy += dy * pull * 0.01;
          p.opacity = Math.min(p.opacity + (1 - dist / 200) * 0.25, 0.5);
        }

        // Damping
        p.vx *= 0.999;
        p.vy *= 0.999;

        // Remove dead or offscreen
        if (p.life >= p.maxLife || p.y < -50 || p.x < -50 || p.x > w + 50) {
          particles.current.splice(i, 1);
          particles.current.push(spawnParticle());
          continue;
        }

        // Draw
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);
        ctx.globalAlpha = p.opacity;
        ctx.fillStyle = "#c4704b";
        ctx.font = `${p.size}px serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.glyph, 0, 0);
        ctx.restore();
      }

      // Connection lines between close particles
      ctx.strokeStyle = "rgba(196, 112, 75, 0.04)";
      ctx.lineWidth = 0.5;
      for (let i = 0; i < particles.current.length; i++) {
        for (let j = i + 1; j < particles.current.length; j++) {
          const a = particles.current[i];
          const b = particles.current[j];
          const d = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
          if (d < 120 && a.opacity > 0.05 && b.opacity > 0.05) {
            ctx.globalAlpha = Math.min(a.opacity, b.opacity) * 0.4;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;

      animationId.current = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      cancelAnimationFrame(animationId.current);
      window.removeEventListener("resize", resize);
      canvas!.removeEventListener("mousemove", handleMouse);
      canvas!.removeEventListener("mouseleave", handleLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "auto",
      }}
    />
  );
}
