import React, { ReactNode } from "react";

interface AldineGutterProps {
  children: ReactNode;
  className?: string;
}

export function AldineGutter({ children, className = "" }: AldineGutterProps) {
  return (
    <aside 
      role="complementary" 
      className={`aldine-hidden lg:aldine-flex aldine-flex-col aldine-gap-4 aldine-pl-6 aldine-border-l aldine-border-bone aldine-text-xs font-interface aldine-ink-muted ${className}`}
    >
      {children}
    </aside>
  );
}




