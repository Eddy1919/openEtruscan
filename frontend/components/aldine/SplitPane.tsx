import React, { ReactNode } from "react";
import { Box } from "./Layout";

interface AldineSplitPaneProps {
  leftPane: ReactNode;
  rightPane: ReactNode;
  initialRatio?: number;
}

export function AldineSplitPane({ leftPane, rightPane, initialRatio = 38.2 }: AldineSplitPaneProps) {
  // Use the initialRatio if provided, otherwise default to golden ratio 38.2/61.8
  const leftWidth = `${initialRatio}%`;
  const rightWidth = `${100 - initialRatio}%`;

  return (
    <Box className="aldine-w-full aldine-flex aldine-flex-col lg:aldine-grid aldine-grow" style={{ gridTemplateColumns: `${leftWidth} ${rightWidth}` }}>
      <Box border="right" surface="canvas" className="aldine-relative aldine-border-b lg:aldine-border-b-0 aldine-min-h-[40vh] lg:aldine-min-h-0">
        <div className="aldine-h-full aldine-w-full aldine-overflow-y-auto">
          {leftPane}
        </div>
      </Box>
      <Box surface="bone" className="aldine-relative aldine-grow aldine-overflow-y-auto">
        {rightPane}
      </Box>
    </Box>
  );
}
