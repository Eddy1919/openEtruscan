"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Box, Row } from "./Layout";

/**
 * SelectionEruption: A floating toolbar that appears above selected text.
 * Provides quick access to scholarly Restore/Classify operations.
 */
export function AldineSelectionEruption() {
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [selectionText, setSelectionText] = useState<string>("");

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    const handleSelection = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed || selection.toString().trim() === "") {
          setPosition(null);
          setSelectionText("");
          return;
        }

        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        const x = rect.left + rect.width / 2;
        const y = rect.top - 10; // offset slightly above the text

        setPosition({ x, y });
        setSelectionText(selection.toString().trim());
      }, 150);
    };

    document.addEventListener("selectionchange", handleSelection);
    return () => {
      document.removeEventListener("selectionchange", handleSelection);
      clearTimeout(timeout);
    };
  }, []);

  if (!position) return null;

  return createPortal(
    <Box
      style={{ top: position.y, left: position.x }}
      className="aldine-fixed aldine-z-overlay aldine-eruption py-1.5 px-3 aldine-bg-ink aldine-canvas aldine-shadow-lg aldine-center aldine-gap-3 aldine-font-interface aldine-text-xs aldine-font-medium"
    >
      <button className="hover:aldine-accent aldine-transition-colors aldine-flex aldine-items-center aldine-gap-2">
         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
         Normalize
      </button>
      <Box className="aldine-w-line aldine-h-3 aldine-bg-bone opacity-20"></Box>
      <button className="hover:aldine-accent aldine-transition-colors aldine-flex aldine-items-center aldine-gap-2">
         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z"/></svg>
         Classify
      </button>
      <Box className="aldine-w-line aldine-h-3 aldine-bg-bone opacity-20"></Box>
      <span className="opacity-50 aldine-measure-xs truncate aldine-w-12 aldine-inline">{selectionText}</span>
    </Box>,
    document.body
  );
}




