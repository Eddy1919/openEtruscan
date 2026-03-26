import Link from "next/link";
import styles from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div className={styles.brand}>
          <span style={{ color: "var(--text-primary)" }}>𐌏𐌐𐌄𐌍</span>
          <span style={{ color: "var(--accent)" }}>Etruscan</span>
        </div>
        <div className={styles.links}>
          <a
            href="https://github.com/Eddy1919/openEtruscan"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
          >
            Hugging Face
          </a>
          <a
            href="https://pypi.org/project/openetruscan/"
            target="_blank"
            rel="noopener noreferrer"
          >
            PyPI
          </a>
          <Link href="/docs">Documentation</Link>
          <Link href="/manifesto">Manifesto</Link>
        </div>
        <div className={styles.licence}>
          Code: MIT &middot; Data: CC0 1.0 &middot; Models: Apache 2.0
        </div>
      </div>
    </footer>
  );
}
