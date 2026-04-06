"use client";

import { useEffect, useState, useMemo, useCallback, useRef, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import type { Inscription, StatsSummary } from "@/lib/corpus";
import { searchCorpus, fetchStatsSummary } from "@/lib/corpus";
import { AldineIndexCard } from "@/components/aldine/IndexCard";
import { AldineSelect } from "@/components/aldine/Select";
import { Ornament } from "@/components/aldine/Layout";

const CLASSIFICATIONS = [
  "funerary", "votive", "dedicatory", "legal",
  "commercial", "boundary", "ownership", "unknown",
];

const PAGE_SIZE = 50;
type SortKey = "relevance" | "date" | "site" | "id";

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [results, setResults] = useState<Inscription[]>([]);
  const [total, setTotal] = useState(0);
  
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [activeClass, setActiveClass] = useState<string | null>(searchParams.get("class") || null);
  const [sortBy, setSortBy] = useState<SortKey>((searchParams.get("sort") as SortKey) || "relevance");
  
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [page, setPage] = useState(1);
  
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const loaderRef = useRef<HTMLDivElement | null>(null);

  // Sync URL State
  useEffect(() => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (activeClass) params.set("class", activeClass);
    if (sortBy !== "relevance") params.set("sort", sortBy);

    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [query, activeClass, sortBy, pathname, router]);

  useEffect(() => {
    fetchStatsSummary().then(setStats).catch(console.error);
  }, []);

  const doSearch = useCallback(
    (text: string, classification: string | null, sortKey: SortKey, currentPage: number) => {
      if (currentPage === 1) setLoading(true);
      const offset = (currentPage - 1) * PAGE_SIZE;
      searchCorpus({
        text: text || undefined,
        classification: classification || undefined,
        limit: PAGE_SIZE,
        offset: offset,
        sort_by: sortKey,
      })
        .then((res) => {
          if (currentPage === 1) {
            setResults(res.results);
          } else {
            setResults(prev => [...prev, ...res.results]);
          }
          setTotal(res.total);
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    },
    []
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query, activeClass, sortBy, page);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, activeClass, sortBy, page, doSearch]);

  useEffect(() => {
    const target = loaderRef.current;
    if (!target) return;

    const observer = new IntersectionObserver((entries) => {
      const first = entries[0];
      if (first.isIntersecting && !loading && results.length < total) {
        setPage((prev) => prev + 1);
      }
    }, { rootMargin: "200px" });
    
    observer.observe(target);
    return () => { observer.disconnect(); };
  }, [loading, results.length, total]);

  const facets = useMemo(() => {
    if (!stats || !Array.isArray(stats.classification_counts)) return [];
    return CLASSIFICATIONS
      .map((cls) => {
        const item = stats.classification_counts.find((x: any) => 
          (Array.isArray(x) && x[0] === cls) || (x.classification === cls)
        );
        const count = item ? (Array.isArray(item) ? item[1] : (item as any).count) : 0;
        return { cls, count };
      })
      .filter((f) => f.count > 0);
  }, [stats]);

  const sortOptions = [
    { value: "relevance", label: "By Relevance" },
    { value: "date", label: "Chronological" },
    { value: "site", label: "By Findspot" },
    { value: "id", label: "By Identifier" },
  ];

  return (
    <div className="aldine-w-full aldine-canvas">
      <article className="aldine-manuscript">
        <header className="aldine-flex-col aldine-border-b" style={{ padding: 'var(--aldine-space-xl) var(--aldine-space-md)', marginBottom: 'var(--aldine-space-xl)' }}>
          <span 
            className="aldine-ink-muted aldine-font-interface" 
            style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 'var(--aldine-space-sm)', display: 'block' }}
          >
            Digital Archive
          </span>
          <h1 className="aldine-display-title" style={{ fontStyle: 'italic', marginBottom: 'var(--aldine-space-xl)' }}>
            Corpus Index
          </h1>
          
          <div className="aldine-relative" style={{ marginBottom: 'var(--aldine-space-xl)' }}>
             <input
               type="text"
               placeholder="Search textual corpus via Old Italic or English..."
               value={query}
               onChange={(e) => { setQuery(e.target.value); setPage(1); }}
               className="aldine-textfield"
               autoFocus
             />
          </div>

          <nav className="aldine-flex-row aldine-justify-between aldine-items-center aldine-border-t aldine-font-interface aldine-text-sm" style={{ paddingTop: 'var(--aldine-space-md)', marginTop: 'var(--aldine-space-xl)', gap: 'var(--aldine-space-lg)' }}>
             
             <div className="aldine-flex-row aldine-items-center" style={{ gap: 'var(--aldine-space-sm)', overflowX: 'auto', paddingBottom: 'var(--aldine-space-sm)', scrollbarWidth: 'none' }}>
                <span className="aldine-ink" style={{ marginRight: 'var(--aldine-space-sm)', flexShrink: 0, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Filter</span>
                <button
                   className="aldine-transition"
                   style={{ 
                      flexShrink: 0, padding: '0.25rem 0.75rem', borderRadius: '9999px', border: '1px solid',
                      borderColor: !activeClass ? 'var(--aldine-ink)' : 'var(--aldine-hairline)',
                      color: !activeClass ? 'var(--aldine-ink)' : 'var(--aldine-ink-muted)',
                      fontWeight: !activeClass ? 600 : 400
                   }}
                   onClick={() => { setActiveClass(null); setPage(1); }}
                >
                   All
                </button>
                {facets.map(({ cls }) => (
                   <button
                     key={cls}
                     className="aldine-transition"
                     style={{ 
                        flexShrink: 0, padding: '0.25rem 0.75rem', borderRadius: '9999px', border: '1px solid', textTransform: 'capitalize',
                        borderColor: activeClass === cls ? 'var(--aldine-accent)' : 'var(--aldine-hairline)',
                        color: activeClass === cls ? 'var(--aldine-accent)' : 'var(--aldine-ink-muted)',
                        fontWeight: activeClass === cls ? 600 : 400
                     }}
                     onClick={() => { setActiveClass(cls); setPage(1); }}
                   >
                     {cls}
                   </button>
                ))}
             </div>

             <div className="aldine-flex-row aldine-items-center" style={{ gap: 'var(--aldine-space-md)', flexShrink: 0 }}>
                <AldineSelect 
                  label="Sort"
                  options={sortOptions}
                  value={sortBy}
                  onChange={(val) => { setSortBy(val as SortKey); setPage(1); }}
                />
             </div>

          </nav>
        </header>

        {loading && page === 1 ? (
           <div className="aldine-flex-col aldine-items-center aldine-justify-center aldine-border-t aldine-border-b" style={{ padding: 'var(--aldine-space-3xl) var(--aldine-space-lg)' }}>
              <Ornament.Label>Retrieving Aldines</Ornament.Label>
              <div className="aldine-ink-muted aldine-font-editorial aldine-italic" style={{ marginTop: 'var(--aldine-space-md)', fontSize: '1.25rem' }}>
                 Opening Manuscript...
              </div>
           </div>
        ) : (
          <div className="aldine-flex-col aldine-gap-0">
             {results.length > 0 ? (
               results.map((insc) => (
                  <AldineIndexCard
                    key={insc.id}
                    id={insc.id}
                    classification={insc.classification}
                    findspot={insc.findspot}
                    canonical={insc.canonical}
                  />
               ))
             ) : (
               <div className="aldine-flex-col aldine-items-center aldine-border-b" style={{ padding: 'var(--aldine-space-2xl) var(--aldine-space-lg)' }}>
                 <p className="aldine-font-editorial aldine-ink-muted" style={{ fontSize: '1.25rem', fontStyle: 'italic' }}>
                   No fragments align with the active inquiry.
                 </p>
               </div>
             )}

             {results.length < total && (
               <div ref={loaderRef} className="aldine-flex-col aldine-items-center aldine-accent aldine-font-interface" style={{ padding: 'var(--aldine-space-xl) 0', fontSize: '0.75rem', letterSpacing: '0.2em', textTransform: 'uppercase' }}>
                 Unrolling scroll...
               </div>
             )}
          </div>
        )}
      </article>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={
       <div className="aldine-w-full aldine-canvas aldine-flex-col aldine-items-center aldine-justify-center" style={{ minHeight: '60vh' }}>
          <Ornament.Label className="aldine-animate-pulse">Loading Corpus Indices</Ornament.Label>
       </div>
    }>
       <SearchContent />
    </Suspense>
  );
}
