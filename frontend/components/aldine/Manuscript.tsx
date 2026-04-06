import React from "react";
import { Box } from "./Layout";

interface AldineManuscriptProps {
  children: React.ReactNode;
  align?: "left" | "center";
  className?: string;
}

/**
 * Manuscript: The scholarly readable canvas for the OpenEtruscan platform.
 * It uses a specialized aldine-manuscript-layout to ensure perfect typography 
 * and measure regardless of the browser window size.
 */
export function AldineManuscript({ children, align = "left", className = "" }: AldineManuscriptProps) {
  return (
    <Box className={`aldine-grid aldine-manuscript-layout aldine-p-6 md:aldine-p-12 ${className}`}>
      <Box className="aldine-col-start-2 aldine-measure m-0 prose-Aldine aldine-ink-base">
        {children}
      </Box>
    </Box>
  );
}




