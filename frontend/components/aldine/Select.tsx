"use client";

import React, { useState, useRef, useEffect } from "react";
import { Box } from "./Layout";

interface DropdownOption {
  label: string;
  value: string;
}

interface AldineSelectProps {
  label?: string;
  options: DropdownOption[];
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  width?: string;
}

export function AldineSelect({ label, options, value, onChange, placeholder = "Select...", width }: AldineSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  return (
    <div className="aldine-flex-col aldine-gap-1" style={{ width: width || "auto", minWidth: "120px" }} ref={containerRef}>
      {label && (
        <label className="aldine-font-interface aldine-ink-muted aldine-uppercase aldine-tracking-widest" style={{ fontSize: "0.65rem", fontWeight: 700, marginBottom: '2px' }}>
          {label}
        </label>
      )}
      
      <div className="aldine-relative aldine-w-full">
        {/* Native Select (Visible only on touch devices, invisible but clickable) */}
        <select
          className="lg:aldine-hidden aldine-absolute aldine-inset-0 aldine-opacity-0 aldine-cursor-pointer"
          style={{ width: '100%', height: '100%', zIndex: 5 }}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Custom UI Trigger */}
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="aldine-w-full aldine-transition aldine-flex-row aldine-justify-between aldine-items-baseline"
          style={{ 
            fontSize: "1.125rem", 
            fontFamily: "var(--font-display)",
            cursor: "pointer", 
            borderBottom: "1px solid",
            borderColor: isOpen ? "var(--aldine-accent)" : "var(--aldine-hairline)",
            padding: "0.25rem 0",
            color: selectedOption ? "var(--aldine-ink)" : "var(--aldine-ink-muted)",
            textAlign: 'left',
            gap: '1rem',
            position: 'relative'
          }}
        >
          <span style={{ 
            whiteSpace: 'nowrap', 
            overflow: 'hidden', 
            textOverflow: 'ellipsis',
            maxWidth: 'calc(100% - 20px)'
          }}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          <svg 
            width="10" height="6" viewBox="0 0 10 6" fill="none" 
            style={{ 
              transform: isOpen ? "rotate(180deg)" : "none", 
              transition: "transform 0.2s", 
              opacity: 0.5,
              flexShrink: 0,
              marginBottom: '4px'
            }}
          >
            <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        {/* Custom UI Dropdown Menu (Desktop only) */}
        {isOpen && (
          <Box 
            surface="bone" 
            border="all" 
            className="aldine-absolute aldine-shadow-lg lg:aldine-block aldine-animate-scale"
            style={{ 
              top: "calc(100% + 8px)", 
              left: 0, 
              zIndex: 1000,
              maxHeight: "350px",
              overflowY: "auto",
              padding: "6px",
              minWidth: "max-content",
              minHeight: "100%",
              width: "auto",
              backdropFilter: 'blur(12px)',
              backgroundColor: 'rgba(250, 250, 249, 0.95)'
            }}
          >
            {options.map((opt, i) => (
              <button
                key={opt.value}
                type="button"
                className={`aldine-w-full aldine-transition aldine-flex-row aldine-items-center aldine-animate-in aldine-stagger-${Math.min(i + 1, 5)}`}
                style={{
                  padding: "10px 16px",
                  textTransform: "none",
                  fontWeight: value === opt.value ? 600 : 400,
                  color: value === opt.value ? "var(--aldine-accent)" : "var(--aldine-ink)",
                  textAlign: "left",
                  fontSize: "0.95rem",
                  fontFamily: "var(--font-inter)",
                  borderRadius: "4px",
                  whiteSpace: 'nowrap'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--aldine-glass)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
              >
                {opt.label}
              </button>
            ))}
          </Box>
        )}
      </div>
    </div>
  );
}




