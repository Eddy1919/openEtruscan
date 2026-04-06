"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  loadLanguages,
  normalize,
  switchLanguage,
  SOURCE_SYSTEM_NAMES,
  type NormalizeResult,
  type LanguageData,
} from "@/lib/normalizer";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineSelect } from "@/components/aldine/Select";
import { AldineSplitPane } from "@/components/aldine/SplitPane";
import { AldineToggle } from "@/components/aldine/Toggle";

const EXAMPLES = [
  { label: "CIE Transcription", text: "MI AVILES" },
  { label: "Philological Text", text: "laris θanχvilus" },
  { label: "Old Italic", text: "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔" },
];

export default function NormalizerPage() {
  const [ready, setReady] = useState(false);
  const [input, setInput] = useState("");
  const [langId, setLangId] = useState("etruscan");
  const [langs, setLangs] = useState<Record<string, LanguageData> | null>(null);
  const [result, setResult] = useState<NormalizeResult | null>(null);
  const [isStrict, setIsStrict] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadLanguages().then((l) => {
      setLangs(l);
      setReady(true);
    });
  }, []);

  const handleInput = useCallback(
    (text: string) => {
      setInput(text);
      if (!ready || !text.trim()) {
        setResult(null);
        return;
      }
      setResult(normalize(text));
      
      if (textareaRef.current) {
         textareaRef.current.style.height = "auto";
         textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
      }
    },
    [ready]
  );

  const handleLangChange = useCallback(
    (id: string) => {
      setLangId(id);
      switchLanguage(id);
      if (input.trim()) {
        setResult(normalize(input));
      }
    },
    [input]
  );

  const InputLayer = (
     <Stack gap={12} className="aldine-canvas aldine-w-full aldine-h-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 'var(--aldine-space-xl)' }}>
           <Stack gap={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Philological Laboratory</Ornament.Label>
           <h1 className="aldine-display-title aldine-italic" style={{ fontSize: '2.25rem' }}>
             Script Normalizer
           </h1>
           <p className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.125rem', opacity: 0.7 }}>
             Lossless translation between Epigraphic and Unicode spaces.
           </p>
        </Stack>

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
             onChange={(e) => handleInput(e.target.value)}
             placeholder="Inject epigraphic context..."
             rows={2}
           />

           <Stack gap={8} border="top" style={{ paddingTop: 'var(--aldine-space-2xl)' }}>
                 <Stack gap={3}>
                    <span className="aldine-font-interface aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>Historical Model</span>
                    <AldineSelect 
                       options={langs ? Object.entries(langs).map(([id, lang]) => ({ label: lang.displayName, value: id })) : []}
                       value={langId}
                       onChange={handleLangChange}
                    />
                 </Stack>

                 <Stack gap={4}>
                    <span className="aldine-font-interface aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>Standard Samples</span>
                    <Row gap={4} style={{ flexWrap: 'wrap' }}>
                      {EXAMPLES.map(ex => (
                         <button 
                           key={ex.label}
                           onClick={() => handleInput(ex.text)}
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
                       label="Strict Orthography"
                       description="Enforce standard CIE mapping for ambiguous characters"
                       value={isStrict}
                       onChange={setIsStrict}
                    />
                 </Box>
           </Stack>
        </Stack>
        </div>
     </Stack>
  );

  const AnalysisLayer = (
     <Stack gap={12} surface="bone" className="aldine-h-full aldine-w-full aldine-overflow-y-auto" style={{ padding: '2rem var(--aldine-space-xl)' }}>
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 'var(--aldine-space-xl)' }}>
           <Stack gap={4} border="bottom" padding={4} className="aldine-animate-in aldine-stagger-1" style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
           <Ornament.Label className="aldine-accent">Normalized Fragments</Ornament.Label>
           <h2 className="aldine-display-title aldine-italic" style={{ fontSize: '1.5rem' }}>Transcription Apparatus</h2>
        </Stack>

        {!result ? (
           <Box className="aldine-flex-col aldine-items-center aldine-justify-center aldine-grow aldine-animate-in aldine-stagger-2">
              <span className="aldine-font-editorial aldine-ink-muted aldine-italic" style={{ fontSize: '1.25rem', opacity: 0.3, textAlign: 'center' }}>
                 Normalizer engine awaiting payload. <br/>
                 Enter historical text to synthesize.
              </span>
           </Box>
        ) : (
           <Stack gap={16} className="aldine-animate-in aldine-stagger-2">
              <Box border="all" padding={6} surface="canvas">
                 <p className="aldine-font-interface aldine-uppercase aldine-accent" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>
                    Detected System: <span style={{ color: 'var(--aldine-ink)', fontWeight: 900, marginLeft: '0.5rem' }}>{SOURCE_SYSTEM_NAMES[result.source_system] || result.source_system}</span>
                 </p>
              </Box>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4rem', borderTop: '1px solid var(--aldine-hairline)', paddingTop: '4rem' }}>
                 <Box style={{ flex: '1 1 200px' }}>
                    <ModelOutput title="Canonical Transcription" text={result.canonical} font="editorial" size="1.5rem" />
                 </Box>
                 <Box style={{ flex: '1 1 200px' }}>
                    <ModelOutput title="Old Italic Graphemes" text={result.old_italic} font="display" size="1.5rem" color="var(--aldine-accent)" />
                 </Box>
                 <Box style={{ flex: '1 1 200px' }}>
                    <ModelOutput title="ASCII Approximation" text={result.web_safe} font="mono" size="0.75rem" />
                 </Box>
                 <Box style={{ flex: '1 1 200px' }}>
                    <ModelOutput title="Phonetic Topology" text={result.phonetic} font="interface" size="1.125rem" />
                 </Box>
              </div>

              <Box surface="canvas" border="all" padding={12} className="aldine-animate-in aldine-stagger-3">
                 <div style={{ marginBottom: 'var(--aldine-space-lg)', opacity: 0.5, display: 'block' }}><Ornament.Label>Morphological Segmentation</Ornament.Label></div>
                 <Row gap={6} style={{ flexWrap: 'wrap' }}>
                    {result.tokens.map((t, i) => (
                      <span key={i} className="aldine-font-mono aldine-ink-base" style={{ fontSize: '0.875rem', padding: '0.5rem 0.75rem', backgroundColor: 'var(--aldine-bone)', border: '1px solid var(--aldine-hairline)', borderRadius: '2px', opacity: 0.8 }}>
                         {t}
                      </span>
                    ))}
                 </Row>
                 
                 {result.warnings.length > 0 && (
                    <Stack gap={4} border="top" padding={8} style={{ marginTop: '4rem' }}>
                       <h4 className="aldine-font-interface aldine-uppercase aldine-accent" style={{ fontSize: '0.75rem', fontWeight: 900, letterSpacing: '0.1em' }}>Mapping Discrepancies</h4>
                       <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {result.warnings.map((w, i) => (
                            <li key={i} className="aldine-font-editorial aldine-ink-base" style={{ fontSize: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                               <span className="aldine-accent">/</span> {w}
                            </li>
                          ))}
                       </ul>
                    </Stack>
                 )}
              </Box>
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

function ModelOutput({ title, text, font, size, color }: { title: string, text: string, font: string, size: string, color?: string }) {
   return (
      <Stack gap={4} className="aldine-group">
         <Box border="bottom" padding={2} style={{ marginBottom: 'var(--aldine-space-xs)', position: 'relative' }}>
            <h4 className="aldine-font-interface aldine-uppercase aldine-ink-muted" style={{ fontSize: '0.625rem', fontWeight: 600, letterSpacing: '0.2em' }}>{title}</h4>
            <button 
               onClick={() => navigator.clipboard.writeText(text)}
               className="aldine-transition"
               style={{ 
                  position: 'absolute', top: 0, right: 0, 
                  background: 'none', border: 'none', cursor: 'pointer',
                  opacity: 0, padding: '2px', color: 'var(--aldine-accent)'
               }}
               title="Copy to clipboard"
            >
               <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
            </button>
            <style>{`.aldine-group:hover button { opacity: 1 !important; }`}</style>
         </Box>
         <p className={`aldine-font-${font} aldine-ink-base`} style={{ color, fontSize: size, lineHeight: 1.6, wordBreak: 'break-word' }}>
            {text || "-"}
         </p>
      </Stack>
   );
}
