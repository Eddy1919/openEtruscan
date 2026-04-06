"use client";

import Link from "next/link";
import { AldineManuscript } from "@/components/aldine/Manuscript";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";

const DOWNLOADS = [
  {
    title: "Complete Corpus Sync",
    filename: "corpus.json",
    url: "https://api.openetruscan.com/corpus",
    size: "~6.8 MB",
    description: "Architectural JSON sync of 11,361 inscriptions generated directly from the PostgreSQL cloud instance. Includes canonical matrices, ML classifications, LOD connections, and WGS84 spatial anchors.",
    format: "JSON Data",
  },
  {
    title: "Graph Database (Turtle)",
    filename: "corpus.ttl",
    url: "https://github.com/Eddy1919/openEtruscan/raw/main/data/rdf/corpus.ttl",
    size: "~1.6 MB",
    description: "Resource Description Framework graph compiled via LAWD, DC, and GeoSPARQL rulesets. Inscriptions modelled as `lawd:WrittenWork` nodes.",
    format: "TTL Graph",
  },
  {
    title: "CNN Topography (ONNX)",
    filename: "cnn.onnx",
    path: "/models/cnn.onnx",
    size: "111 KB",
    description: "1D Convolutional Neural Network execution graph. Rapid 5ms inference resolving 7 distinct epigraphic probabilities directly within WASM constraints.",
    format: "ONNX Weights",
  },
  {
    title: "1-Layer Transformer (ONNX)",
    filename: "transformer.onnx",
    path: "/models/transformer.onnx",
    size: "1.2 MB",
    description: "Selaldine-attention encoder mapping complex linguistic dependencies across character grids. Optimized for multi-word syntax.",
    format: "ONNX Weights",
  },
  {
    title: "Semantic Tables",
    filename: "languages.json",
    path: "/data/languages.json",
    size: "~12 KB",
    description: "Orthographic logic arrays encompassing alphabet matrices, digraph substitutions, and strict unicode conversion rules.",
    format: "JSON Standard",
  },
];

export default function DownloadsPage() {
  return (
    <Box surface="canvas" className="aldine-grow aldine-flex aldine-col aldine-py-16">
      <AldineManuscript align="center">
        
        <Box border="bottom" padding={8} className="aldine-mb-16 aldine-text-center md:aldine-text-left">
          <h1 className="aldine-text-4xl md:aldine-text-5xl aldine-font-display aldine-font-medium aldine-ink-base aldine-italic aldine-mb-4">
            Payload Exports
          </h1>
          <p className="aldine-font-editorial aldine-text-lg aldine-ink-muted aldine-leading-relaxed">
            All matrices, graph bindings, and neural weights are strictly open. (CC0 Data, Apache 2.0 Models, MIT Systems).
          </p>
        </Box>

        <Box className="aldine-flex aldine-col aldine-gap-12 aldine-mb-24">
          {DOWNLOADS.map((d) => {
            const href = d.path || d.url || "#";
            const isExternal = !!d.url;
            return (
              <a
                key={d.filename}
                href={href}
                download={d.path ? d.filename : undefined}
                target={isExternal ? "_blank" : undefined}
                rel={isExternal ? "noopener noreferrer" : undefined}
                className="aldine-flex aldine-col aldine-gap-4 aldine-border aldine-border-bone aldine-bg-bone aldine-p-8 hover:aldine-border-accent aldine-transition-colors group"
              >
                <Row justify="between" align="start" border="bottom" padding={4} className="aldine-flex-col md:aldine-flex-row aldine-gap-2">
                   <h3 className="aldine-font-display aldine-font-medium aldine-text-2xl aldine-ink-base group-hover:aldine-accent aldine-transition-colors">{d.title}</h3>
                   <span className="aldine-font-mono aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest aldine-ink-muted aldine-bg-canvas aldine-px-2 aldine-py-1 aldine-border aldine-border-bone">
                      {d.format}
                   </span>
                </Row>
                
                <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
                  {d.description}
                </p>
                
                <Row justify="between" align="center" border="top" padding={4} className="aldine-mt-4 aldine-font-mono aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest">
                   <span className="aldine-accent">{d.filename}</span>
                   <span className="aldine-ink-muted">{d.size}</span>
                </Row>
              </a>
            );
          })}
        </Box>

        <Box className="aldine-mb-24">
          <h2 className="aldine-text-xl aldine-font-display aldine-font-medium aldine-ink-base aldine-mb-6 aldine-border-b aldine-pb-4">Server APIs</h2>
          <Stack gap={6}>
             <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
               Execute pipeline normalizations via standard POST protocols pointing to the <Link href="/api/normalize" className="aldine-accent aldine-underline hover:aldine-ink-base aldine-transition-colors">Server Compute Node</Link>:
             </p>
             <pre className="aldine-bg-ink aldine-p-6 aldine-border aldine-border-ink aldine-font-mono aldine-text-[11px] md:aldine-text-xs aldine-leading-relaxed aldine-canvas aldine-overflow-x-auto shadow-inner">
{`curl -X POST https://www.openetruscan.com/api/normalize \\
  -H "Content-Type: application/json" \\
  -d '{"text": "MI AVILES"}'`}
             </pre>
             <p className="aldine-font-editorial aldine-text-sm aldine-ink-muted aldine-mt-2">
               Execute internal Python frameworks locally via <code className="aldine-font-mono aldine-bg-bone aldine-px-1 aldine-py-0.5 aldine-border aldine-border-bone aldine-mx-1">pip install openetruscan</code>. Root source located on <a href="https://github.com/Eddy1919/openEtruscan" target="_blank" rel="noopener noreferrer" className="aldine-accent aldine-underline">GitHub</a>.
             </p>
          </Stack>
        </Box>

      </AldineManuscript>
    </Box>
  );
}





