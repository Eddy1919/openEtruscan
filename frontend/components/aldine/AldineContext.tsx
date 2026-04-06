"use client";

import React, { createContext, useContext, useState } from "react";

interface AldineContextType {
  isXmlView: boolean;
  setXmlView: (v: boolean) => void;
  toggleXmlView: () => void;
}

const AldineContext = createContext<AldineContextType | undefined>(undefined);

export function AldineProvider({ children }: { children: React.ReactNode }) {
  const [isXmlView, setXmlView] = useState(false);

  const toggleXmlView = () => setXmlView(v => !v);

  return (
    <AldineContext.Provider value={{ isXmlView, setXmlView, toggleXmlView }}>
      {children}
    </AldineContext.Provider>
  );
}

export function useAldine() {
  const context = useContext(AldineContext);
  if (context === undefined) {
    throw new Error("useAldine must be used within a AldineProvider");
  }
  return context;
}




