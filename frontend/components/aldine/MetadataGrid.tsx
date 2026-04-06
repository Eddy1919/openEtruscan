import React from "react";
import { Box, Row } from "./Layout";

interface AldineMetadataGridProps {
  data: { label: string; value: string | React.ReactNode }[];
}

export function AldineMetadataGrid({ data }: AldineMetadataGridProps) {
  return (
    <Box as="div" role="table" arialdine-label="Metadata" className="aldine-w-full aldine-text-base aldine-font-interface leading-relaxed">
       {data.map((row, i) => (
         <Row role="row" key={i} border="bottom" padding={4} className="last:aldine-border-none">
            <Box as="div" role="rowheader" className="aldine-w-1-3 aldine-ink-muted aldine-font-medium">
              {row.label}
            </Box>
            <Box as="div" role="cell" className="aldine-w-2-3 aldine-ink-base">
              {row.value}
            </Box>
         </Row>
       ))}
    </Box>
  );
}




