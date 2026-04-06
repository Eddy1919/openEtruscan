import Link from "next/link";
import { Row, Box, Stack } from "./aldine/Layout";

export default function Footer() {
  return (
    <Box as="footer" border="top" surface="bone" padding={6} className="aldine-w-full aldine-mt-auto">
      <Row justify="between" align="center" gap={6} className="aldine-measure aldine-mx-auto aldine-px-4 aldine-flex-col lg:aldine-flex-row">
        <Link href="/" className="aldine-font-display aldine-bold aldine-text-xl aldine-flex-row aldine-items-center aldine-gap-1 aldine-group">
          <span className="aldine-ink-base aldine-transition-all group-hover:aldine-accent">𐌏𐌐𐌄𐌍</span>
          <span className="aldine-accent">Etruscan</span>
        </Link>
        
        <Row gap={6} className="aldine-flex-wrap aldine-justify-center aldine-text-sm aldine-bold">
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            target="_blank"
            rel="noopener noreferrer"
            className="aldine-ink-base hover:aldine-accent aldine-transition-all"
          >
            GitHub
          </a>
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
            className="aldine-ink-base hover:aldine-accent aldine-transition-all"
          >
            Hugging Face
          </a>
          <a
            href="https://pypi.org/project/openetruscan/"
            target="_blank"
            rel="noopener noreferrer"
            className="aldine-ink-base hover:aldine-accent aldine-transition-all"
          >
            PyPI
          </a>
          <Link href="/docs" className="aldine-ink-base hover:aldine-accent aldine-transition-all">Documentation</Link>
          <Link href="/manifesto" className="aldine-ink-base hover:aldine-accent aldine-transition-all">Manifesto</Link>
        </Row>
        
        <Box className="aldine-text-xs aldine-ink-muted aldine-text-center lg:aldine-text-right">
          Code: MIT &middot; Data: CC0 1.0 &middot; Models: Apache 2.0
        </Box>
      </Row>
    </Box>
  );
}

