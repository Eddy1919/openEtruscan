import React, { ReactNode } from "react";

interface AldineEntityProps {
  children: ReactNode;
  type: "location" | "person" | "date" | "deity" | "funerary" | "votive" | "dedicatory" | "legal" | "commercial" | "boundary" | "ownership" | "unknown";
  uri?: string;
}

export function AldineEntity({ children, type, uri }: AldineEntityProps) {
  let borderColor = "var(--aldine-hairline)";
  let color = "var(--aldine-ink)";
  
  if (type === "location") borderColor = "var(--aldine-accent)";
  else if (type === "funerary") borderColor = "var(--aldine-accent)";
  else if (type === "person") borderColor = "#6B5A53";
  else if (type === "date") borderColor = "#8E706A";
  else if (type === "unknown") {
     borderColor = "var(--aldine-hairline)";
     color = "var(--aldine-ink-muted)";
  } else {
     borderColor = "var(--aldine-ink-muted)";
  }

  return (
    <mark
      data-type={type}
      title={uri ? `Normalized to: ${uri}` : undefined}
      style={{
         backgroundColor: 'transparent',
         display: 'inline',
         fontWeight: 500,
         borderBottom: `1px solid ${borderColor}`,
         cursor: 'help',
         color: color,
         transition: 'background-color 0.2s',
      }}
      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--aldine-bone)'}
      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
    >
      {children}
    </mark>
  );
}




