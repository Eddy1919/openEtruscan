"use client";

import { useState, useCallback, useRef } from "react";
import {
  loadAndClassify,
  CLASS_DESCRIPTIONS,
  type ClassifierOutput,
} from "@/lib/classifier";
import { CLASS_COLORS } from "@/lib/corpus";
import { AldineSplitPane } from "@/components/aldine/SplitPane";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineToggle } from "@/components/aldine/Toggle";

const EXAMPLES = [
  { text: "mi araθia velθurus", desc: "Ownership mark" },
  { text: "arnθ cutnas zilcte lupu", desc: "Funerary (magistrate death)" },
  { text: "turce menrvas alpan", desc: "Votive offering" },
  { text: "tular rasna spural", desc: "Boundary marker" },
];

export default function ClassifierPage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [cnnResult, setCnnResult] = useState<ClassifierOutput | null>(null);
  const [tfResult, setTfResult] = useState<ClassifierOutput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExplainable, setIsExplainable] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const classify = useCallback(async (text: string) => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setCnnResult(null);
    setTfResult(null);

    try {
      const [cnn, tf] = await Promise.all([
        loadAndClassify(text, "cnn"),
        loadAndClassify(text, "transformer"),
      ]);
      setCnnResult(cnn);
      setTfResult(tf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Classification failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = () => classify(input);
  
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
       textareaRef.current.style.height = "auto";
       textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const InputLayer = (
     <Stack gap={8} className="aldine-canvas aldine-w-full aldine-h-full aldine-overflow-y-auto" style={{ padding: 'var(--aldine-space-2xl)' }}>
        <div style={{ maxWidth: '420px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 'var(--aldine-space-lg)' }}>
           <Stack gap={2} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-xl)' }}>
           <Ornament.Label className="aldine-accent">Philological Laboratory</Ornament.Label>
           <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '1.5rem' }}>
             Neural Topology Classifier
           </h1>
           <p className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '0.875rem', opacity: 0.7 }}>
             Evaluate Etruscan epigraphic records via local ONNX synthesis.
           </p>
        </Stack>

        {error && (
          <Box surface="bone" border="left" padding={4} style={{ borderLeftColor: 'var(--aldine-accent)' }}>
            <span className="aldine-font-interface aldine-accent" style={{ fontSize: '0.75rem', fontWeight: 600 }}>{error}</span>
          </Box>
        )}

        <Stack gap={8} className="aldine-grow aldine-animate-in aldine-stagger-2">
           <textarea
             ref={textareaRef}
             className="aldine-textfield aldine-w-full"
             style={{ 
                fontSize: '1rem', 
                padding: 'var(--aldine-space-sm)',
                resize: 'none',
                overflow: 'hidden'
             }}
             value={input}
             onChange={handleInput}
             onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSubmit())}
             placeholder="Inject epigraphic payload..."
             rows={2}
           />

           <Stack gap={6} border="top" style={{ paddingTop: 'var(--aldine-space-lg)' }}>
                 <Stack gap={4}>
                    <span className="aldine-font-interface aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>Predefined Contexts</span>
                    <Row gap={4} style={{ flexWrap: 'wrap' }}>
                      {EXAMPLES.map(ex => (
                         <button 
                           key={ex.text}
                           onClick={() => { setInput(ex.text); classify(ex.text); }}
                           className="aldine-font-interface aldine-ink-muted aldine-transition"
                           style={{ 
                             fontSize: '0.75rem', 
                             paddingBottom: '2px', 
                             borderBottom: '1px solid var(--aldine-hairline)',
                             cursor: 'pointer'
                           }}
                           onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--aldine-accent)'; e.currentTarget.style.borderColor = 'var(--aldine-accent)'; }}
                           onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--aldine-ink-muted)'; e.currentTarget.style.borderColor = 'var(--aldine-hairline)'; }}
                         >
                           {ex.text}
                         </button>
                      ))}
                    </Row>
                 </Stack>

                 <Box border="all" padding={4} surface="bone">
                    <AldineToggle 
                       label="Explainable Mode"
                       description="Visualize intermediate tensor probability distributions"
                       value={isExplainable}
                       onChange={setIsExplainable}
                    />
                 </Box>

                 <button
                    className="aldine-font-interface aldine-transition"
                    style={{
                       backgroundColor: 'var(--aldine-ink)',
                       color: 'var(--aldine-canvas)',
                       padding: 'var(--aldine-space-md) var(--aldine-space-2xl)',
                       textTransform: 'uppercase',
                       letterSpacing: '0.1em',
                       fontWeight: 600,
                       fontSize: '0.75rem',
                       cursor: (loading || !input.trim()) ? 'not-allowed' : 'pointer',
                       opacity: (loading || !input.trim()) ? 0.5 : 1,
                       alignSelf: 'flex-start'
                    }}
                    disabled={!input.trim() || loading}
                    onClick={handleSubmit}
                    onMouseEnter={e => { if(!loading && input.trim()) e.currentTarget.style.backgroundColor = 'var(--aldine-accent)'; }}
                    onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--aldine-ink)'; }}
                 >
                    {loading ? "Engaging Tensor Stream..." : "Compile Inferences"}
                 </button>
           </Stack>
        </Stack>
        </div>
     </Stack>
  );

  const AnalysisLayer = (
     <Stack gap={12} surface="bone" className="aldine-h-full aldine-w-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <div style={{ maxWidth: '840px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 'var(--aldine-space-xl)' }}>
           <Stack gap={4} border="bottom" padding={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Output Matrices</Ornament.Label>
           <h2 className="aldine-display-title aldine-italic" style={{ fontSize: '1.5rem' }}>Laboratory Evaluation</h2>
        </Stack>

        {!cnnResult && !tfResult ? (
           <Box className="aldine-flex-col aldine-items-center aldine-justify-center aldine-grow aldine-animate-in aldine-stagger-2">
              <span className="aldine-font-editorial aldine-ink-muted aldine-italic" style={{ fontSize: '1.25rem', opacity: 0.3, textAlign: 'center' }}>
                 Neural engine awaits initialization. <br/>
                 Inject epigraphic contexts to begin.
              </span>
           </Box>
        ) : (
           <Stack gap={16} className="aldine-animate-in aldine-stagger-2">
              {cnnResult && tfResult && (
                 <Box border="all" padding={6} surface={cnnResult.predictions[0].label === tfResult.predictions[0].label ? 'bone' : 'canvas'} className={cnnResult.predictions[0].label === tfResult.predictions[0].label ? '' : 'aldine-border-accent'}>
                    <p className="aldine-font-interface aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em', color: cnnResult.predictions[0].label === tfResult.predictions[0].label ? 'var(--aldine-ink-muted)' : 'var(--aldine-accent)' }}>
                       {cnnResult.predictions[0].label === tfResult.predictions[0].label ? (
                          <>Architectural Consensus Documented: <span style={{ color: 'var(--aldine-ink)', fontWeight: 900, marginLeft: '0.5rem' }}>{cnnResult.predictions[0].label}</span></>
                       ) : (
                          <>Structural Discrepancy Observed: {cnnResult.predictions[0].label} × {tfResult.predictions[0].label}</>
                       )}
                    </p>
                 </Box>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', borderTop: '1px solid var(--aldine-hairline)', paddingTop: '2rem' }}>
                 <Box>
                    <ModelMatrix result={cnnResult} title="Character CNN" experimental={isExplainable} />
                 </Box>
                 <Box>
                    <ModelMatrix result={tfResult} title="Linguistic Transformer" experimental={isExplainable} />
                 </Box>
              </div>
           </Stack>
        )}
        </div>
     </Stack>
  );

  return (
     <Box className="aldine-w-full aldine-grow aldine-flex aldine-flex-col" style={{ minHeight: "calc(100vh - 84px)" }}>
        <AldineSplitPane leftPane={InputLayer} rightPane={AnalysisLayer} initialRatio={0.35} />
     </Box>
  );
}

function ModelMatrix({ result, title, experimental }: { result: ClassifierOutput | null, title: string, experimental: boolean }) {
  if (!result) return null;
  const top = result.predictions[0];
  const topColor = CLASS_COLORS[top.label] || CLASS_COLORS.unknown;

  return (
    <Stack gap={8}>
       <Stack gap={2} border="bottom" padding={6} style={{ marginBottom: 'var(--aldine-space-xl)' }}>
          <Row justify="between" align="start" style={{ marginBottom: 'var(--aldine-space-xs)' }}>
             <h3 className="aldine-font-interface aldine-uppercase" style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.1em' }}>{title}</h3>
             <span className="aldine-font-mono aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.625rem', letterSpacing: '0.1em', backgroundColor: 'var(--aldine-canvas)', padding: '2px 8px', border: '1px solid var(--aldine-hairline)', borderRadius: '2px' }}>
               {result.inferenceMs.toFixed(1)}ms
             </span>
          </Row>
          <span className="aldine-font-mono aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.5rem', letterSpacing: '0.1em', opacity: 0.6 }}>{result.arch}</span>
       </Stack>
       
       <Stack gap={2}>
          <Row justify="between" align="end" style={{ marginBottom: 'var(--aldine-space-xs)' }}>
             <span className="aldine-display-title aldine-uppercase" style={{ fontSize: '2.25rem', letterSpacing: '-0.02em', color: topColor }}>
                {top.label}
             </span>
             <span className="aldine-font-mono aldine-ink-base" style={{ fontSize: '1.25rem', opacity: 0.5 }}>
                {(top.probability * 100).toFixed(1)}%
             </span>
          </Row>
          <p className="aldine-font-editorial aldine-ink-muted aldine-leading-relaxed" style={{ fontSize: '0.875rem', height: '2.5rem', overflow: 'hidden' }}>
             {CLASS_DESCRIPTIONS[top.label] || "Unknown Epigraphic Class"}
          </p>
       </Stack>
       
       {experimental && (
          <Stack gap={4} className="aldine-animate-in aldine-stagger-3" style={{ marginTop: 'var(--aldine-space-xl)' }}>
             {result.predictions.slice(0, 5).map(({ label, probability }) => {
                const color = CLASS_COLORS[label] || CLASS_COLORS.unknown;
                const pct = probability * 100;
                return (
                   <Stack key={label} gap={1} className="aldine-group">
                      <Row justify="between" className="aldine-font-interface aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.1em' }}>
                        <span className="aldine-ink-muted aldine-transition" style={{ color: pct > 40 ? 'var(--aldine-ink)' : 'inherit' }}>{label}</span>
                        <span className="aldine-font-mono" style={{ color }}>{pct.toFixed(1)}%</span>
                      </Row>
                      <Box style={{ width: '100%', height: '1px', backgroundColor: 'var(--aldine-hairline)', position: 'relative', overflow: 'hidden' }}>
                        <div className="aldine-transition" style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: `${pct}%`, backgroundColor: color, transitionDuration: '1000ms' }} />
                      </Box>
                   </Stack>
                );
             })}
          </Stack>
       )}
    </Stack>
  );
}
