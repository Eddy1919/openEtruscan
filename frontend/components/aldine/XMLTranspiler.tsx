"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAldine } from "./AldineContext";
import { AldineCode } from "./Code";
import { Box } from "./Layout";

interface AldineXMLTranspilerProps {
  xml: string;
  children: React.ReactNode;
}

/**
 * XMLTranspiler: The digital bridge between typeset aesthetics 
 * and the raw TEI-XML data structure.
 */
export function AldineXMLTranspiler({ xml, children }: AldineXMLTranspilerProps) {
  const { isXmlView } = useAldine();

  return (
    <Box className="aldine-relative aldine-w-full">
      <AnimatePresence mode="wait">
        {isXmlView ? (
          <motion.div
            key="xml"
            initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -10, filter: "blur(4px)" }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <AldineCode 
              language="xml" 
              className="aldine-shadow-inner aldine-bg-bone/20"
            >
              {xml}
            </AldineCode>
          </motion.div>
        ) : (
          <motion.div
            key="content"
            initial={{ opacity: 0, scale: 0.99, filter: "blur(4px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.99, filter: "blur(4px)" }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </Box>
  );
}




