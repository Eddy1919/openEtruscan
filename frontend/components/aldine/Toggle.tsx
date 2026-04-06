"use client";

import React from "react";

interface AldineToggleProps {
  value: boolean;
  onChange: (val: boolean) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
}

/**
 * AldineToggle: A premium, sliding toggle switch.
 * Employs a physical tactile aesthetic (Terracotta slider on Bone track).
 */
export function AldineToggle({ value, onChange, label, description, disabled = false }: AldineToggleProps) {
  return (
    <div 
      className={`aldine-flex-col ${disabled ? 'aldine-opacity-40 aldine-pointer-events-none' : ''}`}
    >
      <div 
        className="aldine-flex-row aldine-items-center aldine-gap-3"
        style={{ cursor: 'pointer' }}
        onClick={() => onChange(!value)}
      >
        <div 
          className="aldine-relative aldine-transition-all aldine-duration-300 aldine-ease-in-out"
          style={{ 
            width: '32px', 
            height: '18px', 
            backgroundColor: value ? 'var(--aldine-terracotta)' : 'var(--aldine-bone)', 
            border: '1px solid var(--aldine-hairline)',
            borderRadius: '9999px',
            boxShadow: value ? 'inset 0 1px 3px rgba(0,0,0,0.1)' : 'none'
          }}
        >
          <div 
            className="aldine-absolute aldine-top-px aldine-transition-all aldine-duration-300 aldine-ease-in-out"
            style={{ 
              width: '14px', 
              height: '14px', 
              backgroundColor: value ? 'var(--aldine-canvas)' : 'var(--aldine-ink-muted)', 
              borderRadius: '50%',
              left: value ? '15px' : '1px',
              boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
            }} 
          />
        </div>
        {label && (
          <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest aldine-ink-muted">
            {label}
          </span>
        )}
      </div>
      {description && (
        <p className="aldine-text-[9px] aldine-font-editorial aldine-italic aldine-ink-muted aldine-mt-1 aldine-ml-11">
          {description}
        </p>
      )}
    </div>
  );
}
