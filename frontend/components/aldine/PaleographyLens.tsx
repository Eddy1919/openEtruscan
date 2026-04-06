"use client";

import { useState, useRef, useEffect } from "react";
import { Box, Ornament } from "./Layout";

interface AldinePaleographyLensProps {
  children?: React.ReactNode;
  type?: "hicontrast" | "inverted" | "spectral";
  radius?: number;
  active?: boolean;
  scale?: number;
  blur?: string;
  className?: string;
}

export function AldinePaleographyLens({ 
  children,
  type = "hicontrast", 
  radius = 60,
  active = true,
  scale = 1.1,
  blur = "0px",
  className = ""
}: AldinePaleographyLensProps) {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleGlobalMouseMove = (e: MouseEvent) => {
      if (!containerRef.current || !active) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      setPosition({ x, y });
      setIsVisible(
        e.clientX >= rect.left && 
        e.clientX <= rect.right && 
        e.clientY >= rect.top && 
        e.clientY <= rect.bottom
      );
    };

    window.addEventListener("mousemove", handleGlobalMouseMove);
    return () => window.removeEventListener("mousemove", handleGlobalMouseMove);
  }, [active]);

  const filterMap = {
    hicontrast: "contrast(2.5) grayscale(100%)",
    inverted: "invert(1) contrast(1.5)",
    spectral: "hue-rotate(90deg) saturate(3)"
  };

  return (
    <div 
      ref={containerRef} 
      className={`aldine-relative aldine-inline-block ${className}`}
    >
      {children}
      {active && isVisible && (
        <div 
          className="aldine-absolute aldine-pointer-events-none aldine-rounded-full aldine-border aldine-border-hairline aldine-shadow-[0_0_20px_rgba(43,33,30,0.1)] aldine-z-portal aldine-overflow-hidden"
          style={{
            left: position.x - radius,
            top: position.y - radius,
            width: radius * 2,
            height: radius * 2,
            backdropFilter: `${filterMap[type] || filterMap.hicontrast} blur(${blur})`,
            transform: `scale(${scale})`,
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid var(--aldine-terracotta-alpha)'
          }}
        >
          {/* Label mini-tag */}
          <div className="aldine-absolute aldine-bottom-1 aldine-left-1/2 aldine--translate-x-1/2 aldine-bg-canvas/80 aldine-px-1 aldine-rounded-[2px] aldine-border aldine-border-hairline">
             <span className="aldine-accent aldine-text-[6px] aldine-uppercase aldine-font-bold aldine-tracking-tighter">
                {type}
             </span>
          </div>
        </div>
      )}
    </div>
  );
}




