"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Stack, Row, Ornament } from "./Layout";

interface AldineChronosRangeProps {
  min: number;
  max: number;
  value: [number, number]; // [TPQ, TAQ]
  onChange: (value: [number, number]) => void;
  uncertainty?: number; // ± years for "circa"
  distribution?: number[]; // Data points for the sparkline
}

export function AldineChronosRange({
  min,
  max,
  value,
  onChange,
  uncertainty = 25,
  distribution = []
}: AldineChronosRangeProps) {
  const [tpq, setTpq] = useState(value[0]);
  const [taq, setTaq] = useState(value[1]);
  const trackRef = useRef<HTMLDivElement>(null);

  const getPercent = (v: number) => ((v - min) / (max - min)) * 100;

  useEffect(() => {
    onChange([tpq, taq]);
  }, [tpq, taq, onChange]);

  const maxDensity = useMemo(() => Math.max(...distribution, 1), [distribution]);

  return (
    <Stack gap={6} className="aldine-w-full aldine-group">
      <Row justify="between" align="baseline" className="aldine-mb-2 aldine-border-b aldine-border-hairline aldine-pb-2">
         <Ornament.Label className="aldine-accent">Chronos Matrix</Ornament.Label>
         <span className="aldine-text-[10px] aldine-font-mono aldine-ink-muted aldine-uppercase aldine-tracking-widest">
           {tpq < 0 ? `${Math.abs(tpq)} BCE` : `${tpq} CE`} - {taq < 0 ? `${Math.abs(taq)} BCE` : `${taq} CE`}
         </span>
      </Row>

      <div className="aldine-relative aldine-pt-8 aldine-pb-4">
        {/* Sparkline Distribution */}
        {distribution.length > 0 && (
          <div className="aldine-absolute aldine-top-0 aldine-left-0 aldine-w-full aldine-h-8 aldine-flex aldine-items-end aldine-opacity-20 aldine-pointer-events-none">
            {distribution.map((d, i) => (
              <div 
                key={i} 
                className="aldine-grow aldine-bg-ink-base" 
                style={{ height: `${(d / maxDensity) * 100}%`, marginRight: '1px' }} 
              />
            ))}
          </div>
        )}

        <div ref={trackRef} className="aldine-relative aldine-w-full aldine-h-line aldine-bg-bone/30">
          {/* Main Range */}
          <div 
            className="aldine-absolute aldine-h-full aldine-bg-terracotta aldine-transition-all aldine-duration-75"
            style={{ 
              left: `${getPercent(tpq)}%`, 
              right: `${100 - getPercent(taq)}%` 
            }}
          />

          {/* Uncertainty Fades (Circa) */}
          <div 
            className="aldine-absolute aldine-h-full aldine-pointer-events-none"
            style={{
              left: `${getPercent(tpq - uncertainty)}%`,
              width: `${getPercent(tpq + uncertainty) - getPercent(tpq - uncertainty)}%`,
              background: `linear-gradient(to right, transparent, rgba(162, 87, 75, 0.4), transparent)`
            }}
          />
          <div 
            className="aldine-absolute aldine-h-full aldine-pointer-events-none"
            style={{
              left: `${getPercent(taq - uncertainty)}%`,
              width: `${getPercent(taq + uncertainty) - getPercent(taq - uncertainty)}%`,
              background: `linear-gradient(to right, transparent, rgba(162, 87, 75, 0.4), transparent)`
            }}
          />

          {/* TPQ Slider */}
          <input
            type="range"
            min={min}
            max={max}
            value={tpq}
            onChange={(e) => setTpq(Math.min(Number(e.target.value), taq - 10))}
            className="aldine-chronos-thumb aldine-chronos-thumb--tpq"
          />
          
          {/* TAQ Slider */}
          <input
            type="range"
            min={min}
            max={max}
            value={taq}
            onChange={(e) => setTaq(Math.max(Number(e.target.value), tpq + 10))}
            className="aldine-chronos-thumb aldine-chronos-thumb--taq"
          />
        </div>

        <Row justify="between" className="aldine-mt-4 aldine-opacity-20 aldine-text-[9px] aldine-font-mono aldine-uppercase aldine-tracking-widest aldine-ink-muted">
           <span>{min}</span>
           <span>{max}</span>
        </Row>
      </div>

      <p className="aldine-text-[9px] aldine-font-editorial aldine-ink-muted aldine-italic aldine-leading-relaxed">
        * Uncertainty offset of ±{uncertainty} years applied to terminus bounds.
      </p>
    </Stack>
  );
}





