"use client";

import GlyphField from "@/components/GlyphField";
import { Button, Card, CardBody, CardHeader } from "@nextui-org/react";

export default function Home() {
  return (
    <main className="flex flex-col min-h-screen">
      {/* Hero with particle background */}
      <section className="relative flex flex-col items-center justify-center text-center overflow-hidden py-32 px-4 border-b border-border bg-background">
        <div className="absolute inset-0 opacity-40 z-0 pointer-events-none">
          <GlyphField />
        </div>
        <div className="relative z-10 max-w-3xl mx-auto flex flex-col items-center gap-6">
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-display font-bold flex gap-3 text-foreground">
            <span className="opacity-80 mix-blend-screen mix-blend-color-dodge">𐌏𐌐𐌄𐌍</span>
            <span className="text-primary font-black drop-shadow-md">Etruscan</span>
          </h1>
          <p className="text-lg sm:text-xl text-muted font-medium max-w-xl">
            An open-source digital corpus and computational toolkit for the study
            of Etruscan epigraphy. MIT / CC0 licensed.
          </p>

          <div className="flex flex-wrap justify-center gap-8 my-8">
            <div className="flex flex-col items-center">
              <span className="text-3xl font-display font-bold text-foreground">4,728</span>
              <span className="text-xs uppercase tracking-widest text-muted font-semibold mt-1">Inscriptions</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-3xl font-display font-bold text-foreground">45</span>
              <span className="text-xs uppercase tracking-widest text-muted font-semibold mt-1">Provenances</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-3xl font-display font-bold text-foreground">41</span>
              <span className="text-xs uppercase tracking-widest text-muted font-semibold mt-1">Pleiades Links</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-3xl font-display font-bold text-foreground">5</span>
              <span className="text-xs uppercase tracking-widest text-muted font-semibold mt-1">Script Systems</span>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-4 mt-4 w-full sm:w-auto">
            <Button
              as="a"
              href="/search"
              color="primary"
              size="lg"
              className="font-bold shadow-lg w-full sm:w-auto"
            >
              Search the Corpus
            </Button>
            <Button
              as="a"
              href="/explorer"
              variant="bordered"
              color="secondary"
              size="lg"
              className="font-bold border-2 w-full sm:w-auto"
            >
              Explore the Map
            </Button>
            <Button
              as="a"
              href="https://github.com/Eddy1919/openEtruscan"
              target="_blank"
              rel="noopener noreferrer"
              variant="bordered"
              size="lg"
              className="font-bold border-2 border-border text-foreground hover:border-foreground w-full sm:w-auto"
            >
              Source Code
            </Button>
          </div>
        </div>
      </section>

      {/* Feature cards */}
      <section className="py-24 px-4 sm:px-6 lg:px-8 max-w-[1200px] mx-auto w-full flex-grow">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="bg-secondary/40 backdrop-blur border border-border hover:border-secondary transition-colors !shadow-none p-4">
            <CardHeader className="flex gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary font-display text-2xl font-bold">
                𐌏
              </div>
              <h3 className="text-xl font-bold font-display text-foreground">Georeferenced Corpus</h3>
            </CardHeader>
            <CardBody>
              <p className="text-muted leading-relaxed">
                Browse 4,700+ inscriptions on an interactive map. Each entry is
                aligned to Pleiades and GeoNames gazetteers for interoperability
                with other ancient-world datasets.
              </p>
            </CardBody>
          </Card>
          
          <Card className="bg-secondary/40 backdrop-blur border border-border hover:border-secondary transition-colors !shadow-none p-4">
            <CardHeader className="flex gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary font-display text-2xl font-bold">
                𐌄
              </div>
              <h3 className="text-xl font-bold font-display text-foreground">Script Normalizer</h3>
            </CardHeader>
            <CardBody>
              <p className="text-muted leading-relaxed">
                Convert between five transcription systems: canonical, CIE,
                philological, Old Italic Unicode (U+10300), and IPA. Includes
                automatic source-system detection.
              </p>
            </CardBody>
          </Card>

          <Card className="bg-secondary/40 backdrop-blur border border-border hover:border-secondary transition-colors !shadow-none p-4">
            <CardHeader className="flex gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary font-display text-2xl font-bold">
                𐌈
              </div>
              <h3 className="text-xl font-bold font-display text-foreground">Neural Classifier</h3>
            </CardHeader>
            <CardBody>
              <p className="text-muted leading-relaxed">
                Character-level neural models (CNN, Transformer) classify
                inscriptions by epigraphic type. Inference runs client-side via
                ONNX Runtime.
              </p>
            </CardBody>
          </Card>

          <Card className="bg-secondary/40 backdrop-blur border border-border hover:border-secondary transition-colors !shadow-none p-4">
            <CardHeader className="flex gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary font-display text-2xl font-bold">
                𐌓
              </div>
              <h3 className="text-xl font-bold font-display text-foreground">Linked Open Data</h3>
            </CardHeader>
            <CardBody>
              <p className="text-muted leading-relaxed">
                The full corpus is exported as RDF/Turtle using LAWD and Dublin
                Core ontologies. A SPARQL endpoint enables cross-corpus queries
                within the Linked Open Data ecosystem.
              </p>
            </CardBody>
          </Card>
        </div>
      </section>
    </main>
  );
}
