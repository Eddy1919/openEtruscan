import { Metadata } from 'next';
import { AldineGlyphField } from "@/components/aldine/GlyphField";
import Link from "next/link";

export const metadata: Metadata = {
  title: "OpenEtruscan | Computational Toolkit & Digital Corpus",
  description: "A collaborative digital humanities initiative for the global mapping, cataloging, and structural analysis of the Etruscan epigraphic record. The definitive open-source standard for classical computational linguistics.",
};

export default function Home() {
  return (
    <main className="aldine-w-full">
      {/* Aldine Hero Canvas */}
      <section className="aldine-relative aldine-w-full aldine-center aldine-border-b" style={{ minHeight: '60vh', overflow: 'hidden' }}>
        <div className="aldine-absolute aldine-inset-0 aldine-opacity-40" style={{ zIndex: 0 }}>
          <AldineGlyphField />
        </div>
        
        <article className="aldine-manuscript aldine-relative aldine-py-12" style={{ textAlign: 'center', zIndex: 10 }}>
           <div className="aldine-flex-col aldine-items-center aldine-gap-6">
              <h1 className="aldine-display-title aldine-animate-in" style={{ lineHeight: 0.9 }}>
                <span className="aldine-font-epigraphic aldine-animate-in aldine-stagger-1" style={{ color: 'var(--aldine-accent)', display: 'block', fontSize: '1.3em', marginBottom: '0.2em' }}>𐌏𐌐𐌄𐌍</span>
                <span className="aldine-animate-in aldine-stagger-2" style={{ fontStyle: 'italic', fontWeight: 300 }}>Etruscan</span>
                <span className="aldine-display-subtitle aldine-animate-in aldine-stagger-3" style={{ display: 'block', marginTop: '1rem' }}>Digital Corpus & Computational Toolkit</span>
              </h1>
             
              <p className="aldine-prose aldine-animate-in aldine-stagger-4" style={{ maxWidth: '65ch', marginInline: 'auto', color: 'var(--aldine-ink-muted)' }}>
                A collaborative digital humanities initiative for the global mapping, cataloging, and structural analysis of the Etruscan epigraphic record. The definitive open-source standard for classical computational linguistics.
              </p>

              <nav className="aldine-flex-row aldine-items-center aldine-gap-6 aldine-pt-12 aldine-animate-in aldine-stagger-5" style={{ letterSpacing: '0.1em', fontSize: '0.875rem', textTransform: 'uppercase' }}>
                <Link
                  href="/search"
                  className="aldine-btn aldine-transition hover:aldine-shadow-lg"
                >
                  Search Corpus
                </Link>
                <span className="aldine-opacity-20" arialdine-hidden="true">|</span>
                <Link
                  href="/explorer"
                  className="aldine-btn aldine-transition hover:aldine-shadow-lg" style={{ borderColor: 'transparent' }}
                >
                  Spatial Atlas
                </Link>
              </nav>
           </div>
        </article>
      </section>

      {/* Toolkit Features Restoration */}
      <section className="aldine-w-full" style={{ padding: '6rem 0', backgroundColor: 'var(--aldine-bone)' }}>
        <article className="aldine-manuscript">
          <header className="aldine-flex-col aldine-items-center aldine-border-b aldine-gap-2 aldine-mb-16 aldine-pb-12" style={{ textAlign: 'center' }}>
             <span className="aldine-font-epigraphic" style={{ fontSize: '0.75rem', color: 'var(--aldine-ink-muted)' }}>Infrastructure</span>
             <h2 className="aldine-display-title" style={{ fontStyle: 'italic' }}>Computational Tools</h2>
          </header>

          <div className="aldine-split-pane">
            
            <article className="aldine-card aldine-p-6 aldine-flex-col aldine-gap-4 aldine-transition hover:aldine-border-accent aldine-animate-in aldine-stagger-1 aldine-text-card-hover" style={{ backgroundColor: 'var(--aldine-canvas)' }}>
               <div className="aldine-flex-row aldine-gap-4 aldine-items-center">
                  <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1.5rem' }}>𐌏</span>
                  <h3 className="aldine-display-subtitle" style={{ fontWeight: 600 }}>Georeferenced Corpus</h3>
               </div>
               <p className="aldine-prose" style={{ fontSize: '0.875rem', color: 'var(--aldine-ink-muted)' }}>
                  Browse 4,700+ inscriptions on an interactive map. Each entry is aligned to Pleiades and GeoNames gazetteers for interoperability with other ancient-world datasets.
               </p>
            </article>

            <article className="aldine-card aldine-p-6 aldine-flex-col aldine-gap-4 aldine-transition hover:aldine-border-accent aldine-animate-in aldine-stagger-2 aldine-text-card-hover" style={{ backgroundColor: 'var(--aldine-canvas)' }}>
               <div className="aldine-flex-row aldine-gap-4 aldine-items-center">
                  <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1.5rem' }}>𐌄</span>
                  <h3 className="aldine-display-subtitle" style={{ fontWeight: 600 }}>Script Normalizer</h3>
               </div>
               <p className="aldine-prose" style={{ fontSize: '0.875rem', color: 'var(--aldine-ink-muted)' }}>
                  Convert between five transcription systems: canonical, CIE, philological, Old Italic Unicode (U+10300), and IPA. Includes automatic source-system detection.
               </p>
            </article>

            <article className="aldine-card aldine-p-6 aldine-flex-col aldine-gap-4 aldine-transition hover:aldine-border-accent aldine-animate-in aldine-stagger-3 aldine-text-card-hover" style={{ backgroundColor: 'var(--aldine-canvas)' }}>
               <div className="aldine-flex-row aldine-gap-4 aldine-items-center">
                  <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1.5rem' }}>𐌈</span>
                  <h3 className="aldine-display-subtitle" style={{ fontWeight: 600 }}>Neural Classifier</h3>
               </div>
               <p className="aldine-prose" style={{ fontSize: '0.875rem', color: 'var(--aldine-ink-muted)' }}>
                  Character-level neural models classify inscriptions by epigraphic type. Inference runs client-side via ONNX Runtime.
               </p>
            </article>

            <article className="aldine-card aldine-p-6 aldine-flex-col aldine-gap-4 aldine-transition hover:aldine-border-accent aldine-animate-in aldine-stagger-4 aldine-text-card-hover" style={{ backgroundColor: 'var(--aldine-canvas)' }}>
               <div className="aldine-flex-row aldine-gap-4 aldine-items-center">
                  <span className="aldine-font-epigraphic aldine-accent" style={{ fontSize: '1.5rem' }}>𐌓</span>
                  <h3 className="aldine-display-subtitle" style={{ fontWeight: 600 }}>Linked Open Data</h3>
               </div>
               <p className="aldine-prose" style={{ fontSize: '0.875rem', color: 'var(--aldine-ink-muted)' }}>
                  The full corpus is exported as RDF/Turtle using LAWD and Dublin Core ontologies. A SPARQL endpoint enables cross-corpus queries within the LOD ecosystem.
               </p>
            </article>

          </div>
        </article>
      </section>

      {/* Dodecapolis Aldine Integration */}
      <section className="aldine-w-full aldine-border-t" style={{ padding: '6rem 0', backgroundColor: 'var(--aldine-canvas)' }}>
        <article className="aldine-manuscript">
          <header className="aldine-flex-col aldine-items-center aldine-border-b aldine-gap-2 aldine-mb-16 aldine-pb-12" style={{ textAlign: 'center' }}>
             <span className="aldine-font-epigraphic" style={{ fontSize: '0.75rem', color: 'var(--aldine-accent)' }}>Topography</span>
             <h2 className="aldine-display-title" style={{ fontStyle: 'italic' }}>The Dodecapolis</h2>
          </header>
          
          <div className="aldine-masonry">
             {[ 
               {name:"Volterrae", id:"volterrae", code:"v"}, 
               {name:"Tarquinii", id:"tarquinii", code:"t"},
               {name:"Caere", id:"caere", code:"c"},
               {name:"Veii", id:"veii", code:"ve"},
               {name:"Vulci", id:"vulci", code:"vu"},
               {name:"Vetulonia", id:"vetulonia", code:"vet"},
               {name:"Clusium", id:"clusium", code:"cl"},
               {name:"Perusia", id:"perusia", code:"p"},
               {name:"Cortona", id:"cortona", code:"co"},
               {name:"Arretium", id:"arretium", code:"a"},
               {name:"Faesulae", id:"faesulae", code:"f"},
               {name:"Populonia", id:"populonia", code:"po"}
             ].map((city, i) => (
               <figure key={city.id} className={`aldine-masonry-item aldine-card aldine-animate-in aldine-stagger-${(i % 5) + 1}`} style={{ backgroundColor: 'var(--aldine-bone)' }}>
                  <Link 
                     href={`/docs/${city.id}`}
                     className="aldine-flex-col aldine-gap-4 aldine-p-6 aldine-group"
                     style={{ display: 'flex' }}
                  >
                     <div className="aldine-flex-row aldine-justify-between">
                        <span className="aldine-font-epigraphic" style={{ color: 'var(--aldine-ink-muted)', fontSize: '0.75rem' }}>[{city.code}]</span>
                        <span className="aldine-group-hover-accent aldine-group-hover-opacity-100 aldine-transition" style={{ opacity: 0.2, color: 'var(--aldine-accent)', fontSize: '1.25rem' }}>𐌄</span>
                     </div>
                     <figcaption className="aldine-display-subtitle aldine-group-hover-accent aldine-transition" style={{ fontStyle: 'italic', fontWeight: 600, color: 'var(--aldine-ink)' }}>{city.name}</figcaption>
                     <p className="aldine-prose aldine-group-hover-opacity-100 aldine-transition" style={{ fontSize: '0.875rem', opacity: 0.6 }}>
                        Primary urban center of the Etruscan League. Epigraphic record includes major funerary and ritual dedications.
                     </p>
                  </Link>
               </figure>
             ))}
          </div>
        </article>
      </section>

    </main>
  );
}
