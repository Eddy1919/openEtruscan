"use client";

import { AldineManuscript } from "@/components/aldine/Manuscript";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";

export default function ManifestoPage() {
  return (
    <Box surface="canvas" className="aldine-grow aldine-flex aldine-col aldine-py-20">
        <AldineManuscript align="center">
          <Box border="bottom" padding={8} style={{ marginBottom: 'var(--aldine-space-3xl)', textAlign: 'center' }} className="aldine-animate-in">
            <h1 className="aldine-font-display aldine-font-medium aldine-ink-base aldine-italic aldine-tracking-tight aldine-animate-in aldine-stagger-1" style={{ fontSize: '4rem', marginBottom: 'var(--aldine-space-2xl)' }}>
              The Manifesto
            </h1>
            <p className="aldine-ink-base aldine-font-editorial aldine-leading-snug aldine-italic aldine-opacity-90 aldine-animate-in aldine-stagger-2" style={{ fontSize: '1.75rem', borderLeft: '4px solid var(--aldine-accent)', paddingLeft: 'var(--aldine-space-xl)', paddingBottom: 'var(--aldine-space-md)', paddingTop: 'var(--aldine-space-md)', margin: '0 auto', maxWidth: '800px', textAlign: 'left' }}>
              "The Etruscan language is one of the least-understood voices in the ancient Mediterranean. As artificial intelligence continues to train on billions of words from modern languages, fragmented ancient tongues risk being left in the dark. We built OpenEtruscan to ensure they survive."
            </p>
          </Box>

          <Stack gap={16} className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.35rem', maxWidth: '800px', margin: '0 auto' }}>
            
            <Stack gap={8} className="aldine-animate-in aldine-stagger-3">
               <h2 className="aldine-font-bold aldine-uppercase aldine-accent aldine-flex aldine-center aldine-hover-expand" style={{ fontSize: '0.875rem', letterSpacing: '0.3em', borderBottom: '1px solid var(--aldine-hairline)', paddingBottom: '1rem' }}>
                 <span className="aldine-font-mono aldine-opacity-50" style={{ marginRight: '1rem' }}>01</span> Empowering the Margins
              </h2>
              <Stack gap={6}>
                 <p>
                   The digital revolution presents a profound challenge for under-resourced fields. Modern machine learning models are inherently dataldine-hungry. Languages with limited training data are largely invisible to them. If we do not actively digitize, computationally structure, and open the epigraphic records of ancient civilizations, their voices will fail to survive the transition into the AI age.
                 </p>
                 <p>
                   OpenEtruscan serves as a structural blueprint for empowering marginalized historical records. We exist to prove that small fields can wield the exact same advanced neural classification and semantic clustering tools currently monopolized by the world's most spoken languages.
                 </p>
              </Stack>
            </Stack>

            <Stack gap={8}>
              <h2 className="aldine-font-bold aldine-uppercase aldine-accent aldine-flex aldine-center" style={{ fontSize: '0.875rem', letterSpacing: '0.3em', borderBottom: '1px solid var(--aldine-hairline)', paddingBottom: '1rem' }}>
                 <span className="aldine-font-mono aldine-opacity-50" style={{ marginRight: '1rem' }}>02</span> Scholarly Accessibility
              </h2>
              <p>
                The foundational texts of Etruscan epigraphy - such as the massive <em>Corpus Inscriptionum Etruscarum</em> (CIE) - are legacy print-era masterworks. Currently, they are locked behind institutional paywalls or geographically bound to physical libraries. OpenEtruscan dismantles these structural barriers by delivering a fully machine-readable execution of the record under highly permissive MIT and CC0 logic schemas.
              </p>
            </Stack>

            <Box surface="bone" border="all" padding={12} style={{ marginTop: 'var(--aldine-space-2xl)' }}>
              <h2 className="aldine-font-display aldine-font-medium aldine-ink-base" style={{ fontSize: '2rem', marginBottom: 'var(--aldine-space-2xl)', paddingBottom: 'var(--aldine-space-lg)', borderBottom: '1px solid var(--aldine-hairline)' }}>The Core Principles</h2>
              <Stack gap={12} style={{ fontSize: '1.125rem' }}>
                <Stack gap={4}>
                  <h3 className="aldine-font-bold aldine-font-interface aldine-uppercase aldine-ink-base aldine-flex aldine-center gap-3" style={{ fontSize: '0.75rem', letterSpacing: '0.1em', gap: '0.75rem' }}>
                    <div className="aldine-bg-accent" style={{ width: '4px', height: '4px', borderRadius: '50%' }} />
                    Open Logic by Default
                  </h3>
                  <p className="aldine-ink-muted" style={{ borderLeft: '1px solid var(--aldine-bone)', paddingLeft: '1.5rem', marginLeft: '1px' }}>The preservation of human history cannot be sequestered behind proprietary logic. Every element - including the data, code interfaces, pipeline architecture, and neural weights - functions as an open construct.</p>
                </Stack>
                <Stack gap={4}>
                  <h3 className="aldine-font-bold aldine-font-interface aldine-uppercase aldine-ink-base aldine-flex aldine-center gap-3" style={{ fontSize: '0.75rem', letterSpacing: '0.1em', gap: '0.75rem' }}>
                    <div className="aldine-bg-accent" style={{ width: '4px', height: '4px', borderRadius: '50%' }} />
                    AI Architectural Precision
                  </h3>
                  <p className="aldine-ink-muted" style={{ borderLeft: '1px solid var(--aldine-bone)', paddingLeft: '1.5rem', marginLeft: '1px' }}>Standard computational tools hallucinate or discard the profound ambiguity of ancient fragments. We explicitly train precise, lightweight networks scaled to execute inference directly within client-side sandboxes.</p>
                </Stack>
                 <Stack gap={4}>
                  <h3 className="aldine-font-bold aldine-font-interface aldine-uppercase aldine-ink-base aldine-flex aldine-center gap-3" style={{ fontSize: '0.75rem', letterSpacing: '0.1em', gap: '0.75rem' }}>
                    <div className="aldine-bg-accent" style={{ width: '4px', height: '4px', borderRadius: '50%' }} />
                    Multidisciplinary Synthesis
                  </h3>
                  <p className="aldine-ink-muted" style={{ borderLeft: '1px solid var(--aldine-bone)', paddingLeft: '1.5rem', marginLeft: '1px' }}>By integrating pure NLP pipelines with spatial archaeogenetics and geospatial rendering grids, we systematically reconstruct the human topologies operating behind the inscriptions.</p>
                </Stack>
              </Stack>
            </Box>

            <Stack gap={8} align="center" justify="center" style={{ paddingTop: 'var(--aldine-space-3xl)', textAlign: 'center' }}>
              <h2 className="aldine-font-display aldine-font-medium aldine-ink-base" style={{ fontSize: '1.5rem' }}>Execution Sequence</h2>
              <p className="aldine-ink-muted" style={{ fontSize: '1.125rem', maxWidth: '65ch' }}>
                By actively demonstrating that cutting-edge AI and classical philology can be seamlessly synthesized for a language with fewer than 10,000 surviving iterations, we establish the matrix for similar resurgent revivals for under-resourced lexicons across the globe.
              </p>
              <p className="aldine-accent aldine-font-display aldine-font-medium aldine-italic" style={{ fontSize: '2.5rem', marginTop: 'var(--aldine-space-2xl)' }}>
                This matrix is open format. Join us.
              </p>
            </Stack>

          </Stack>
       </AldineManuscript>
    </Box>
  );
}





