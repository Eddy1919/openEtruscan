"use client";

import { useState, useMemo, useCallback, useRef, useEffect, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import type { KWICRow } from "@/lib/corpus";
import { fetchConcordance } from "@/lib/corpus";
import { Box, Stack, Row, Ornament } from "@/components/aldine/Layout";
import { AldineSelect } from "@/components/aldine/Select";
import { AldineTable, AldineKWICRow } from "@/components/aldine/Table";
import { AldineSplitPane } from "@/components/aldine/SplitPane";

type SortKey = "left" | "right" | "id";
const CONTEXT_OPTIONS = [20, 40, 60, 80];

function ConcordanceContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [rows, setRows] = useState<KWICRow[]>([]);
  const [uniqueCount, setUniqueCount] = useState(0);
  
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [contextLen, setContextLen] = useState(Number(searchParams.get("ctx")) || 40);
  const [sortBy, setSortBy] = useState<SortKey>((searchParams.get("sort") as SortKey) || "left");

  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Sync URL State
  useEffect(() => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (contextLen !== 40) params.set("ctx", contextLen.toString());
    if (sortBy !== "left") params.set("sort", sortBy);

    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [query, contextLen, sortBy, pathname, router]);

  const doSearch = useCallback(
    (q: string, ctx: number) => {
      // Abort any pending requests
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const trimmed = q.trim();
      if (trimmed.length < 2) {
        setRows([]);
        setUniqueCount(0);
        setSearched(trimmed.length > 0);
        setLoading(false);
        return;
      }
      
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setLoading(true);
      setSearched(true);
      fetchConcordance(trimmed, ctx, 2000, controller.signal)
        .then((res) => {
          setRows(res.rows);
          setUniqueCount(res.unique_inscriptions);
          setLoading(false);
        })
        .catch((e) => {
          if (e.name !== "AbortError") {
            setLoading(false);
            console.error(e);
          }
        });
    },
    []
  );

  // Initial trigger if URL params exist
  useEffect(() => {
    if (query) {
      doSearch(query, contextLen);
    }
  }, []); // Only run once on mount

  const triggerSearch = useCallback(
    (q: string, ctx: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(q, ctx), 400);
    },
    [doSearch]
  );

  const sorted = useMemo(() => {
    const arr = [...rows];
    switch (sortBy) {
      case "left":
        return arr.sort((a, b) => {
          const aEnd = a.left.trim().split(/\s+/).pop() || "";
          const bEnd = b.left.trim().split(/\s+/).pop() || "";
          return aEnd.localeCompare(bEnd);
        });
      case "right":
        return arr.sort((a, b) => {
          const aStart = a.right.trim().split(/\s+/)[0] || "";
          const bStart = b.right.trim().split(/\s+/)[0] || "";
          return aStart.localeCompare(bStart);
        });
      case "id":
        return arr.sort((a, b) => a.inscId.localeCompare(b.inscId));
      default:
        return arr;
    }
  }, [rows, sortBy]);

  const SearchPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-y-auto aldine-px-8 aldine-py-16 aldine-bg-canvas">
        <Box className="aldine-mb-16 aldine-animate-in aldine-stagger-1">
           <Ornament.Label className="aldine-accent">Corpus Index</Ornament.Label>
           <h1 className="aldine-text-4xl md:aldine-text-5xl aldine-font-display aldine-font-medium aldine-ink-base aldine-italic aldine-mb-6">
             Scholarly Concordance
           </h1>
           <p className="aldine-font-editorial aldine-text-lg aldine-ink-base aldine-leading-relaxed aldine-opacity-70">
             Perform Keyword-in-Context (KWIC) analysis across the entire digital corpus.
           </p>
        </Box>

        <Box className="aldine-flex aldine-col aldine-grow aldine-animate-in aldine-stagger-2">
           <input
             type="text"
             className="aldine-w-full aldine-bg-transparent border-none aldine-text-2xl lg:aldine-text-4xl aldine-font-editorial aldine-leading-relaxed aldine-ink-base placeholder-ink-muted/30 aldine-outline-none aldine-border-b aldine-border-bone aldine-pb-1 focus:aldine-border-accent aldine-transition-colors"
             value={query}
             onChange={(e) => {
                setQuery(e.target.value);
                triggerSearch(e.target.value, contextLen);
             }}
             placeholder="Inject query (e.g. laris)..."
           />

           <Box className="aldine-mt-12 aldine-border-t aldine-border-bone aldine-pt-8">
              <Stack gap={8}>
                 <Stack gap={3}>
                    <span className="aldine-text-[10px] aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-ink-muted">Context Radius</span>
                    <AldineSelect 
                       options={CONTEXT_OPTIONS.map(n => ({ label: `${n} characters`, value: n.toString() }))}
                       value={contextLen.toString()}
                       onChange={(val) => {
                          const ctx = Number(val);
                          setContextLen(ctx);
                          triggerSearch(query, ctx);
                       }}
                       width="100%"
                    />
                 </Stack>

                 <Stack gap={3}>
                    <span className="aldine-text-[10px] aldine-uppercase aldine-tracking-[0.2em] aldine-font-bold aldine-ink-muted">Sort Vectors</span>
                    <AldineSelect 
                       options={[
                         { label: "Left Context", value: "left" },
                         { label: "Right Context", value: "right" },
                         { label: "Inscription ID", value: "id" }
                       ]}
                       value={sortBy}
                       onChange={(val) => setSortBy(val as SortKey)}
                       width="100%"
                    />
                 </Stack>

                 {rows.length > 0 && !loading && (
                    <Box border="all" padding={4} className="aldine-bg-bone/30 aldine-border-bone aldine-text-center aldine-animate-in aldine-fade-in">
                       <span className="aldine-text-[10px] aldine-uppercase aldine-font-bold aldine-tracking-widest aldine-accent">
                          Index Matches: {rows.length.toLocaleString()}
                       </span>
                    </Box>
                 )}
              </Stack>
           </Box>
        </Box>
     </Box>
  );

  const ResultsPane = (
     <Box className="aldine-flex aldine-col aldine-h-full aldine-overflow-y-auto aldine-w-full aldine-px-8 aldine-py-16 aldine-bg-bone">
        <Box border="bottom" padding={4} className="aldine-mb-12 aldine-animate-in aldine-stagger-1">
           <Ornament.Label className="aldine-accent">Linguistic Fragments</Ornament.Label>
           <h2 className="aldine-text-2xl aldine-font-display aldine-italic aldine-ink-base">KWIC Alignment Matrix</h2>
        </Box>

        {loading ? (
             <Box className="aldine-flex aldine-col aldine-center aldine-grow aldine-animate-pulse">
                <span className="aldine-text-xs aldine-uppercase aldine-tracking-[0.3em] aldine-font-black aldine-ink-muted">Traversing Textual Indices</span>
             </Box>
        ) : sorted.length > 0 ? (
           <Box className="aldine-animate-in aldine-fade-in">
              <AldineTable 
                headers={["Record", "Context Left", "Keyword", "Context Right"]}
              >
                {sorted.map((row, i) => (
                  <AldineKWICRow 
                    key={`${row.inscId}-${i}`}
                    id={row.inscId}
                    left={row.left}
                    keyword={row.keyword}
                    right={row.right}
                    href={`/inscription/${encodeURIComponent(row.inscId)}`}
                    className={`aldine-animate-in aldine-stagger-${Math.min(i + 1, 5)}`}
                  />
                ))}
              </AldineTable>
           </Box>
        ) : searched && query.trim().length >= 2 ? (
           <Box className="aldine-flex aldine-col aldine-center aldine-grow aldine-opacity-20 aldine-ink-muted aldine-italic aldine-font-editorial aldine-text-xl aldine-text-center">
              Zero occurrences documented in the digital archive.
           </Box>
        ) : (
           <Box className="aldine-flex aldine-col aldine-center aldine-grow aldine-opacity-10 aldine-ink-muted aldine-italic aldine-font-editorial aldine-text-xl aldine-text-center">
              Awaiting textual parameters...
           </Box>
        )}
     </Box>
  );

  return (
     <Box className="aldine-grow aldine-flex aldine-col aldine-h-content">
        <AldineSplitPane leftPane={SearchPane} rightPane={ResultsPane} />
     </Box>
  );
}

export default function ConcordancePage() {
  return (
    <Suspense fallback={
       <div className="aldine-w-full aldine-canvas aldine-flex-col aldine-items-center aldine-justify-center" style={{ minHeight: '60vh' }}>
          <Ornament.Label className="aldine-animate-pulse">Loading Concordance Matrix</Ornament.Label>
       </div>
    }>
       <ConcordanceContent />
    </Suspense>
  )
}
