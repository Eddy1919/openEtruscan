"use client";

import { ChangeEvent, useCallback, useEffect, useState, useRef } from "react";
import { Stack, Row, Ornament } from "./Layout";

interface AldineRangeSliderProps {
  min: number;
  max: number;
  step?: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
  label?: string;
}

export function AldineRangeSlider({ 
  min, 
  max, 
  step = 10, 
  value, 
  onChange, 
  label 
}: AldineRangeSliderProps) {
  const [minVal, setMinVal] = useState(value[0]);
  const [maxVal, setMaxVal] = useState(value[1]);
  const minValRef = useRef(value[0]);
  const maxValRef = useRef(value[1]);
  const range = useRef<HTMLDivElement>(null);

  // Convert to percentage
  const getPercent = useCallback(
    (value: number) => Math.round(((value - min) / (max - min)) * 100),
    [min, max]
  );

  // Set width of the range to decrease from the left side
  useEffect(() => {
    const minPercent = getPercent(minVal);
    const maxPercent = getPercent(maxValRef.current);

    if (range.current) {
      range.current.style.left = `${minPercent}%`;
      range.current.style.width = `${maxPercent - minPercent}%`;
    }
  }, [minVal, getPercent]);

  // Set width of the range to decrease from the right side
  useEffect(() => {
    const minPercent = getPercent(minValRef.current);
    const maxPercent = getPercent(maxVal);

    if (range.current) {
      range.current.style.width = `${maxPercent - minPercent}%`;
    }
  }, [maxVal, getPercent]);

  // Get min and max values when their state changes
  useEffect(() => {
    onChange([minVal, maxVal]);
  }, [minVal, maxVal, onChange]);

  return (
    <Stack gap={6} className="aldine-w-full">
      {label && (
        <Row justify="between" align="baseline" border="bottom" padding={2} className="aldine-mb-2">
           <Ornament.Label>{label}</Ornament.Label>
           <span className="aldine-font-interface aldine-ink-muted" style={{ fontSize: "0.85rem", letterSpacing: "0.05em", fontWeight: 500 }}>
             {Math.abs(minVal)} BCE - {maxVal <= 0 ? `${Math.abs(maxVal)} BCE` : `${maxVal} CE`}
           </span>
        </Row>
      )}
      
      <div className="aldine-relative aldine-w-full aldine-h-1 aldine-bg-bone" style={{ background: 'rgba(107, 105, 98, 0.1)' }}>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={minVal}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const value = Math.min(Number(event.target.value), maxVal - step);
            setMinVal(value);
            minValRef.current = value;
          }}
          className="aldine-thumb aldine-thumb--left"
          style={{ zIndex: 3 }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={maxVal}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const value = Math.max(Number(event.target.value), minVal + step);
            setMaxVal(value);
            maxValRef.current = value;
          }}
          className="aldine-thumb aldine-thumb--right"
          style={{ zIndex: 4 }}
        />

        <div className="aldine-slider">
          <div className="aldine-slider__track" />
          <div ref={range} className="aldine-slider__range aldine-bg-canvas" style={{ backgroundColor: 'var(--aldine-terracotta)' }} />
        </div>
      </div>
    </Stack>
  );
}




