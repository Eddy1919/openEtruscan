import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full bg-background border-t border-border mt-auto py-8">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="font-display font-bold text-xl flex items-center gap-1 group">
          <span className="text-foreground transition-colors group-hover:text-primary">𐌏𐌐𐌄𐌍</span>
          <span className="text-primary">Etruscan</span>
        </div>
        
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm font-medium">
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground hover:text-primary transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground hover:text-primary transition-colors"
          >
            Hugging Face
          </a>
          <a
            href="https://pypi.org/project/openetruscan/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground hover:text-primary transition-colors"
          >
            PyPI
          </a>
          <Link href="/docs" className="text-foreground hover:text-primary transition-colors">Documentation</Link>
          <Link href="/manifesto" className="text-foreground hover:text-primary transition-colors">Manifesto</Link>
        </div>
        
        <div className="text-xs text-muted text-center md:text-right">
          Code: MIT &middot; Data: CC0 1.0 &middot; Models: Apache 2.0
        </div>
      </div>
    </footer>
  );
}
