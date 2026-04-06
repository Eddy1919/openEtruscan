"use client";

import React, { useState } from "react";
import { Box, Stack } from "./Layout";

interface AldineDropdownProps {
  items: {
    title: string;
    description?: string;
    content: React.ReactNode;
    id: string;
  }[];
  className?: string;
}

export function AldineDropdown({ items, className = "" }: AldineDropdownProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <Stack gap={0} className={`aldine-w-full ${className}`}>
      {items.map((item) => {
        const isOpen = openId === item.id;

        return (
          <Box 
            key={item.id} 
            border="bottom" 
            padding={0} 
            className="aldine-border-bone/50 aldine-overflow-hidden"
          >
            <button
              onClick={() => setOpenId(isOpen ? null : item.id)}
              className="aldine-w-full aldine-flex aldine-flex-row aldine-justify-between aldine-items-center aldine-py-6 aldine-hover-bg-bone/20 aldine-transition-colors aldine-text-left aldine-group"
            >
              <Stack gap={1} className="aldine-grow">
                <span className={`aldine-text-lg aldine-font-display aldine-font-medium aldine-transition-colors ${isOpen ? 'aldine-accent' : 'aldine-ink-base aldine-group-hover:aldine-accent'}`}>
                  {item.title}
                </span>
                {item.description && (
                  <span className="aldine-text-xs aldine-font-editorial aldine-ink-muted aldine-italic aldine-opacity-60">
                    {item.description}
                  </span>
                )}
              </Stack>
              <div className={`aldine-transition-transform aldine-duration-300 aldine-mr-2 ${isOpen ? 'rotate-180' : ''}`}>
                 <svg width="12" height="8" viewBox="0 0 10 6" fill="none" style={{ opacity: isOpen ? 0.8 : 0.4 }}>
                    <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                 </svg>
              </div>
            </button>
            <div 
              className={`aldine-transition-all aldine-duration-500 aldine-ease-in-out ${isOpen ? 'aldine-max-h-[1000px] aldine-py-8 aldine-opacity-100' : 'aldine-max-h-0 aldine-opacity-0'}`}
              style={{ overflow: 'hidden' }}
            >
               <div className="aldine-measure-xs aldine-mx-auto">
                  {item.content}
               </div>
            </div>
          </Box>
        );
      })}
    </Stack>
  );
}
