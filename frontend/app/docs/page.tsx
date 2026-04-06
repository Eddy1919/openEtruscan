"use client";

import { AldineManuscript } from "@/components/aldine/Manuscript";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineDropdown } from "@/components/aldine/Accordion";
import { AldineCode } from "@/components/aldine/Code";
import { AldineXMLTranspiler } from "@/components/aldine/XMLTranspiler";
import { AldineCitationBlock } from "@/components/aldine/CitationBlock";

const RESOURCES = [
  {
    title: "Source Code Architecture",
    url: "https://github.com/Eddy1919/openEtruscan",
    description: "Complete monorepo spanning the Python computational backend, Next.js Aldine engine, NLP pipelines, and PyTorch model architectures.",
    cta: "GitHub Repository"
  },
  {
    title: "On-Device Neural Networks",
    url: "https://huggingface.co/Eddy1919/openetruscan-classifier",
    description: "Pre-trained Character-level Convolutional and scaled-down Transformer sequences ported to ONNX for 0-latency inference.",
    cta: "Hugging Face Model Registry"
  },
  {
    title: "Linked Open Data (Resource Description Framework)",
    url: "https://github.com/Eddy1919/openEtruscan/blob/main/data/rdf/corpus.ttl",
    description: "Digital corpus synthesized natively as RDF/Turtle executing on LAWD, Dublin Core, and GeoSPARQL vocabularies.",
    cta: "Retrieve TTL Graph"
  },
  {
    title: "Python Package Index",
    url: "https://pypi.org/project/openetruscan/",
    description: "Programmatic package bindings granting direct instantiation of the normalization and classification submodules.",
    cta: "PyPI Build"
  }
];

const DOCS_XML = `<?xml version="1.0" encoding="UTaldine-8"?>
<teiHeader>
  <fileDesc>
    <titleStmt>
      <title>OpenEtruscan Technical Manual</title>
    </titleStmt>
    <publicationStmt>
      <publisher>OpenEtruscan Project</publisher>
      <availability status="free">
        <licence target="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0 Universal</licence>
      </availability>
    </publicationStmt>
  </fileDesc>
</teiHeader>`;

export default function DocsPage() {
  const accordionItems = [
    {
      id: "schema",
      title: "Data Topology & Schema",
      description: "Core ontological mappings for the digital corpus.",
      content: (
        <Stack gap={8}>
           <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
             OpenEtruscan records are flattened into a high-performance relational schema optimized for spatial queries and graph traversals.
           </p>
           <Box border="top" className="aldine-w-full" role="table">
              <div role="row" className="aldine-grid aldine-grid-cols-4 aldine-gap-4 aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-[0.2em] aldine-ink-muted aldine-py-4 aldine-border-b">
                 <div role="columnheader" className="aldine-col-span-1">Key</div>
                 <div role="columnheader" className="aldine-col-span-1">Type</div>
                 <div role="columnheader" className="aldine-col-span-2">Definition</div>
              </div>
              
              {[
                ["id", "string", "Primary unique key (e.g. Cr 2.20)"],
                ["canonical", "string", "Rigid philological textual standard"],
                ["old_italic", "string?", "Unicode U+10300 mapping"],
                ["phonetic", "string?", "IPA approximate manifestation"],
                ["findspot", "string?", "Geospatial origination marker"],
                ["classification", "string?", "Taxonomic branch"],
              ].map(([f, t, d]) => (
                 <div role="row" key={f} className="aldine-grid aldine-grid-cols-4 aldine-gap-4 aldine-py-4 aldine-border-b aldine-border-bone/50 aldine-font-editorial aldine-text-base">
                    <div role="cell" className="aldine-col-span-1 aldine-font-mono aldine-text-xs aldine-font-bold aldine-accent">{f}</div>
                    <div role="cell" className="aldine-col-span-1 aldine-font-mono aldine-text-[10px] aldine-ink-muted aldine-uppercase">{t}</div>
                    <div role="cell" className="aldine-col-span-2 aldine-ink-base aldine-leading-snug">{d}</div>
                 </div>
              ))}
           </Box>
        </Stack>
      )
    },
    {
      id: "normalization",
      title: "Epigraphic Normalization Spaces",
      description: "Mapping historical diacritics to digital character sets.",
      content: (
        <Stack gap={8}>
           <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
             We support four distinct linguistic layers for every inscription. The normalizer engine provides lossless conversion across these vectors.
           </p>
           <Box className="aldine-grid aldine-grid-cols-1 md:aldine-grid-cols-2 aldine-gap-8 aldine-pt-4">
              {[
                { sys: "CIE Subsystem", ex: "MI AVILES", desc: "Corpus Inscriptionum Etruscarum standards." },
                { sys: "Philological Axiom", ex: "mi avile·s", desc: "Scientific taxonomy enforcing diacritics (θ, φ, χ, ś)." },
                { sys: "Old Italic", ex: "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔", desc: "Native Etruscan symbols on Unicode space." },
                { sys: "Web-Safe ASCII", ex: "mi aviles", desc: "Strictly normalized rendering." }
              ].map((s) => (
                 <Box key={s.sys} border="all" padding={6} className="aldine-bg-bone/20 aldine-border-hairline">
                    <Ornament.Label className="aldine-accent aldine-mb-2">{s.sys}</Ornament.Label>
                    <p className="aldine-font-mono aldine-text-sm aldine-ink-base aldine-mb-2 aldine-font-bold">{s.ex}</p>
                    <p className="aldine-text-xs aldine-font-editorial aldine-ink-muted">{s.desc}</p>
                 </Box>
              ))}
           </Box>
        </Stack>
      )
    },
    {
      id: "neural",
      title: "Neural Network Architectures",
      description: "Computational topologies for classification and recovery.",
      content: (
        <Stack gap={10}>
           <Stack gap={4}>
              <h4 className="aldine-text-xs aldine-font-bold aldine-uppercase aldine-tracking-widest aldine-accent">CharCNN (Inference Optimized)</h4>
              <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
                1D Convolution layers designed for client-side execution via ONNX. Handles sequence-to-class classification for funerary vs votive status.
              </p>
              <AldineCode language="python">
                {`# Model Topology: CharCNN\nlayers = [\n  Conv1d(in_channels=256, out_channels=128, kernel_size=3),\n  MaxPool1d(kernel_size=2),\n  Dropout(0.2),\n  Linear(128, 9) # 9 Taxonomy Classes\n]`}
              </AldineCode>
           </Stack>
           <Stack gap={4}>
              <h4 className="aldine-text-xs aldine-font-bold aldine-uppercase aldine-tracking-widest aldine-accent">Neural Transformer (Lacunae Recovery)</h4>
              <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed">
                Multi-head attention mechanism trained on 12,000 epigraphic fragments to predict spatial character losses.
              </p>
              <AldineCode language="python">
                {`# Attention weights focus on neighboring phonemes\n# to resolve [.] gaps.\nprediction = model.forward(masked_token_index)`}
              </AldineCode>
           </Stack>
        </Stack>
      )
    }
  ];

  return (
    <Box surface="canvas" className="aldine-grow aldine-flex aldine-col aldine-h-content aldine-py-20 aldine-overflow-y-auto">
      <AldineXMLTranspiler xml={DOCS_XML}>
        <AldineManuscript>
          <Box border="bottom" padding={8} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-5xl)' }}>
             <Ornament.Label className="aldine-accent">Technical Apparatus</Ornament.Label>
             <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '3rem', marginBottom: 'var(--aldine-space-xl)' }}>
               The Manuscript Manual
             </h1>
             <p className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.25rem', opacity: 0.7, maxWidth: '48rem' }}>
               Documentation regarding the deployment of client-side logic, ontological mappings, and the neural topologies powering the OpenEtruscan engine.
             </p>
          </Box>

          <Box className="aldine-animate-in aldine-stagger-2" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '3rem', marginBottom: 'var(--aldine-space-5xl)' }}>
             {RESOURCES.map((r) => (
                <Stack key={r.title} gap={3} className="aldine-group">
                   <a href={r.url} target="_blank" rel="noreferrer" className="aldine-flex aldine-center aldine-justify-between aldine-border-b aldine-border-hairline aldine-pb-4 hover:aldine-border-accent aldine-transition-all">
                      <h3 className="aldine-text-xl aldine-font-display aldine-font-medium aldine-ink-base group-hover:aldine-accent aldine-transition-colors">{r.title}</h3>
                      <Row align="center" gap={2} className="aldine-transition-transform group-hover:aldine-translate-x-1">
                         <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest aldine-ink-muted">Access</span>
                         <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="aldine-ink-muted aldine-opacity-30 group-hover:aldine-accent group-hover:aldine-opacity-100">
                            <path d="M2.5 9.5L9.5 2.5M9.5 2.5H4M9.5 2.5V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                         </svg>
                      </Row>
                   </a>
                   <p className="aldine-text-sm aldine-font-editorial aldine-ink-muted aldine-leading-relaxed aldine-opacity-80">{r.description}</p>
                </Stack>
             ))}
          </Box>

          <Box className="aldine-mb-32 aldine-animate-in aldine-stagger-3">
             <AldineDropdown items={accordionItems} />
          </Box>

          <AldineCitationBlock 
            id="DOCS-TECH-001"
            title="OpenEtruscan Technical Manuscript"
          />

          <Stack align="center" justify="center" padding={16} border="top" className="aldine-border-bone aldine-mt-12 aldine-opacity-30 aldine-animate-in aldine-stagger-4">
             <Ornament.Label className="aldine-ink-base aldine-mb-6 aldine-tracking-[0.4em]">Open Knowledge Index</Ornament.Label>
             <Row gap={8} className="aldine-font-mono aldine-text-[10px] aldine-ink-base aldine-font-bold aldine-uppercase aldine-tracking-widest">
                <span className="aldine-border-b aldine-border-hairline">MIT License (Engine)</span>
                <span className="aldine-border-b aldine-border-hairline">CC0 (Corpus Matrix)</span>
             </Row>
          </Stack>
        </AldineManuscript>
      </AldineXMLTranspiler>
    </Box>
  );
}





