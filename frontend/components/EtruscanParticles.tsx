"use client";

import { useEffect, useRef } from "react";

const ETRUSCAN_CHARS = [
  "𐌀", "𐌁", "𐌂", "𐌃", "𐌄", "𐌅", "𐌆", "𐌇", "𐌈", "𐌉", 
  "𐌊", "𐌋", "𐌌", "𐌍", "𐌎", "𐌏", "𐌐", "𐌑", "𐌒", "𐌓", 
  "𐌔", "𐌕", "𐌖", "𐌗", "𐌘", "𐌙", "𐌚"
];

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  char: string;
  opacity: number;
  baseX: number;
  baseY: number;
}

export default function EtruscanParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;
    
    const setSize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * window.devicePixelRatio;
      canvas.height = height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    setSize();
    window.addEventListener("resize", setSize);

    const particles: Particle[] = [];
    const numParticles = Math.min(Math.floor((width * height) / 20000), 100);

    for (let i = 0; i < numParticles; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        baseX: Math.random() * width,
        baseY: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        size: Math.random() * 20 + 10,
        char: ETRUSCAN_CHARS[Math.floor(Math.random() * ETRUSCAN_CHARS.length)],
        opacity: Math.random() * 0.3 + 0.05, // Super subtle
      });
    }

    const mouse = { x: -1000, y: -1000 };
    const handleMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    // Attach listener to window so it tracks correctly
    window.addEventListener("mousemove", handleMouseMove);

    let animationId: number;

    const animate = () => {
      ctx.clearRect(0, 0, width, height);

      particles.forEach((p) => {
        // Base movement
        p.x += p.vx;
        p.y += p.vy;

        // Bounce horizontally
        if (p.x < 0 || p.x > width) p.vx *= -1;
        // Bounce vertically
        if (p.y < 0 || p.y > height) p.vy *= -1;

        // Interaction
        const dx = mouse.x - p.x;
        const dy = mouse.y - p.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const interactionRadius = 250; 

        if (distance < interactionRadius) {
          // Attract towards the mouse gently
          const force = (interactionRadius - distance) / interactionRadius;
          const ax = (dx / distance) * force * 0.2;
          const ay = (dy / distance) * force * 0.2;
          
          p.x += ax;
          p.y += ay;
          
          // Boost opacity near mouse
          p.opacity = Math.min(p.opacity + 0.02, 0.8);
        } else {
          // Slowly decay opacity back to base
          p.opacity = Math.max(p.opacity - 0.01, 0.1);
          
          // Slowly drift back to base velocity if attracted too fast
          p.vx = p.vx * 0.99 + (Math.random() - 0.5) * 0.01;
          p.vy = p.vy * 0.99 + (Math.random() - 0.5) * 0.01;
        }

        // Draw
        ctx.fillStyle = `rgba(227, 66, 52, ${p.opacity})`; // Cinnabar Red
        ctx.font = `${p.size}px "JetBrains Mono", monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.char, p.x, p.y);
      });

      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", setSize);
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="aldine-fixed aldine-inset-0 aldine-w-full aldine-h-full aldine-pointer-events-none aldine-z-0 aldine-mix-blend-multiply aldine-opacity-20"
    />
  );
}

