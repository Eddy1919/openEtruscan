"use client";

import { useState, useRef } from "react";
import { restoreLacunae, type RestoreResponse } from "@/lib/corpus";
import { AldineSplitPane } from "@/components/aldine/SplitPane";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineToggle } from "@/components/aldine/Toggle";

const EXAMPLES = [
  { label: "Middle Gap", text: "suθi lar[..]al lecnes" },
  { label: "Missing Initial", text: "[.]i aviles" },
  { label: "Fragmentary", text: "m[.] api[..]" },
];

export default function LacunaePage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RestoreResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLowProb, setShowLowProb] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleRestore = async (textToRestore: string) => {
    if (!textToRestore.trim()) {
      setResult(null);
      setError(null);
      return;
    }
    
    setLoading(true);
    setError(null);
    setResult(null);
    
    try {
      const response = await restoreLacunae(textToRestore, 5);
      setResult(response);
    } catch (err: any) {
      setError(err.message || "Failed to restore text.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleRestore(input);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
       textareaRef.current.style.height = "auto";
       textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const EditorPane = (
     <Stack gap={12} className="aldine-canvas aldine-w-full aldine-h-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <Stack gap={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Philological Laboratory</Ornament.Label>
           <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '2.25rem' }}>
             Lacunae Restoration
           </h1>
           <p className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.125rem', opacity: 0.7 }}>
             Predict character distributions within epigraphic gaps using ML.
           </p>
        </Stack>

        {error && (
          <Box surface="bone" border="left" padding={4} style={{ borderLeftColor: 'var(--aldine-accent)' }}>
            <span className="aldine-font-interface aldine-accent" style={{ fontSize: '0.75rem', fontWeight: 600 }}>{error}</span>
          </Box>
        )}

        <Stack gap={12} className="aldine-grow aldine-animate-in aldine-stagger-2">
           <textarea
             ref={textareaRef}
             className="aldine-textfield aldine-w-full"
             style={{ 
                fontSize: '1.5rem', 
                padding: 'var(--aldine-space-md) var(--aldine-space-sm)',
                resize: 'none',
                overflow: 'hidden'
             }}
             value={input}
             onChange={handleChange}
             onKeyDown={handleKeyDown}
             placeholder="Inject context... (e.g. suθi lar[..]al)"
             rows={2}
           />

           <Stack gap={8} border="top" style={{ paddingTop: 'var(--aldine-space-2xl)' }}>
                 <Stack gap={4}>
                    <span className="aldine-font-interface aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>Historical Presets</span>
                    <Row gap={4} style={{ flexWrap: 'wrap' }}>
                      {EXAMPLES.map(ex => (
                         <button 
                           key={ex.label}
                           onClick={() => { setInput(ex.text); handleRestore(ex.text); }}
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
                           {ex.label}
                         </button>
                      ))}
                    </Row>
                 </Stack>

                 <Box border="all" padding={4} surface="bone">
                    <AldineToggle 
                       label="Extensive Analysis"
                       description="Visualize low-probability linguistic edge cases"
                       value={showLowProb}
                       onChange={setShowLowProb}
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
                    onClick={() => handleRestore(input)}
                    onMouseEnter={e => { if(!loading && input.trim()) e.currentTarget.style.backgroundColor = 'var(--aldine-accent)'; }}
                    onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--aldine-ink)'; }}
                 >
                    {loading ? "Computing Probability..." : "Execute Neural Recovery"}
                 </button>
           </Stack>

           <Box border="top" padding={4} style={{ marginTop: 'auto' }}>
              <div style={{ marginBottom: 'var(--aldine-space-sm)', opacity: 0.3 }}><Ornament.Label>Leiden Conventions</Ornament.Label></div>
              <ul className="aldine-font-editorial aldine-ink-muted" style={{ paddingLeft: 'var(--aldine-space-md)', opacity: 0.5, fontSize: '0.875rem' }}>
                 <li style={{ marginBottom: 'var(--aldine-space-xs)' }}>Bounded gaps like <code className="aldine-font-mono" style={{ backgroundColor: 'var(--aldine-bone)', padding: '0 4px' }}>[.]</code> map 1:1 to spatial character losses.</li>
                 <li>Dual loss <code className="aldine-font-mono" style={{ backgroundColor: 'var(--aldine-bone)', padding: '0 4px' }}>[..]</code> triggers multi-step inference.</li>
              </ul>
           </Box>
        </Stack>
     </Stack>
  );

  const AnalysisPane = (
     <Stack gap={12} surface="bone" className="aldine-h-full aldine-w-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <Stack gap={4} border="bottom" padding={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Inference Matrix</Ornament.Label>
           <h2 className="aldine-display-title aldine-italic" style={{ fontSize: '1.5rem' }}>Probability Distributions</h2>
        </Stack>

        {!result ? (
           <Box className="aldine-flex-col aldine-items-center aldine-justify-center aldine-grow aldine-animate-in aldine-stagger-2">
              <span className="aldine-font-editorial aldine-ink-muted aldine-italic" style={{ fontSize: '1.25rem', opacity: 0.3, textAlign: 'center' }}>
                 Linguistic engine idle. <br/>
                 Awaiting textual parameters.
              </span>
           </Box>
        ) : (
           <Stack gap={12} className="aldine-animate-in aldine-stagger-2">
              <Box surface="canvas" border="all" padding={6}>
                 <div style={{ marginBottom: 'var(--aldine-space-sm)' }}><Ornament.Label>Observed Context</Ornament.Label></div>
                 <p className="aldine-font-editorial aldine-ink-base" style={{ fontSize: '1.25rem' }}>{result.text}</p>
              </Box>

              {result.predictions && result.predictions.length > 0 ? (
                 <Stack gap={8}>
                    {result.predictions.map((pred, i) => (
                       <Box key={i} surface="canvas" border="all" padding={6} className="aldine-animate-in" style={{ animationDelay: `${i * 100}ms` }}>
                          <Box border="bottom" style={{ paddingBottom: 'var(--aldine-space-sm)', marginBottom: 'var(--aldine-space-xl)' }}>
                             <Ornament.Label className="aldine-accent">
                                Gap Vector Array: Index {pred.position}
                             </Ornament.Label>
                          </Box>
                          
                          <Stack gap={6}>
                             {Object.entries(pred.predictions)
                                .sort((a, b) => b[1] - a[1])
                                .filter(([char, prob]) => showLowProb ? true : prob > 0.05)
                                .map(([char, prob]) => {
                                   const pct = Math.round(prob * 100);
                                   return (
                                      <Stack key={char} gap={2} className="aldine-group">
                                         <Row justify="between" align="end">
                                            <span className="aldine-display-title aldine-ink-base aldine-transition" style={{ fontSize: '1.5rem' }}>{char}</span>
                                            <span className="aldine-font-mono aldine-ink-muted" style={{ fontSize: '0.875rem' }}>{pct}%</span>
                                         </Row>
                                         <Box style={{ width: '100%', height: '1px', backgroundColor: 'var(--aldine-hairline)', position: 'relative', overflow: 'hidden' }}>
                                            <div 
                                              className="aldine-transition"
                                              style={{ 
                                                 position: 'absolute', top: 0, left: 0, height: '100%', 
                                                 width: `${pct}%`, 
                                                 backgroundColor: pct > 40 ? 'var(--aldine-accent)' : 'var(--aldine-ink-muted)',
                                                 opacity: Math.max(0.2, prob),
                                                 transitionDuration: '1000ms'
                                              }} 
                                            />
                                         </Box>
                                      </Stack>
                                   );
                                })}
                          </Stack>
                       </Box>
                    ))}
                 </Stack>
              ) : (
                 <Box padding={6} border="all" className="aldine-flex-col aldine-items-center">
                    <span className="aldine-font-editorial aldine-ink-muted aldine-italic" style={{ opacity: 0.5, textAlign: 'center' }}>
                       Neural engine detected no valid gaps `[.]` in the buffer.
                    </span>
                 </Box>
              )}
           </Stack>
        )}
     </Stack>
  );

  return (
     <Box className="aldine-grow aldine-flex aldine-col" style={{ minHeight: 'calc(100vh - 84px)' }}>
        <AldineSplitPane leftPane={EditorPane} rightPane={AnalysisPane} initialRatio={0.35} />
     </Box>
  );
}
