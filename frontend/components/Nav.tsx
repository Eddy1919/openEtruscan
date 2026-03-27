"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Nav.module.css";

const PRIMARY = [
  { href: "/search", label: "Search" },
  { href: "/concordance", label: "Concordance" },
  { href: "/explorer", label: "Explorer" },
];

const TOOLS = [
  { href: "/normalizer", label: "Normalizer" },
  { href: "/compare", label: "Compare" },
  { href: "/timeline", label: "Timeline" },
  { href: "/names", label: "Names" },
];

const REFERENCE = [
  { href: "/stats", label: "Statistics" },
  { href: "/downloads", label: "Downloads" },
  { href: "/docs", label: "Docs" },
];

function Dropdown({
  label,
  items,
  pathname,
}: {
  label: string;
  items: { href: string; label: string }[];
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const isActive = items.some((i) => i.href === pathname);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={ref} className={styles.dropdown}>
      <button
        className={`nav-pill${isActive ? " active" : ""} ${styles.dropBtn}`}
        onClick={() => setOpen(!open)}
      >
        {label}
        <span className={styles.caret}>&#9662;</span>
      </button>
      {open && (
        <div className={styles.dropMenu}>
          {items.map(({ href, label: itemLabel }) => (
            <Link
              key={href}
              href={href}
              className={`${styles.dropItem} ${pathname === href ? styles.dropItemActive : ""}`}
              onClick={() => setOpen(false)}
            >
              {itemLabel}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav-bar">
      <Link href="/" className="nav-brand" style={{ textDecoration: "none" }}>
        <span style={{ color: "var(--text-primary)" }}>𐌏𐌐𐌄𐌍</span>
        <span style={{ color: "var(--accent)" }}>Etruscan</span>
      </Link>
      <ul className="nav-pills">
        {[...PRIMARY, { href: "/classifier", label: "Classifier" }, { href: "/genetics", label: "Genetics" }].map(({ href, label }) => (
          <li key={href}>
            <Link
              href={href}
              className={`nav-pill${pathname === href ? " active" : ""}`}
            >
              {label}
            </Link>
          </li>
        ))}
        <li>
          <Dropdown label="Tools" items={TOOLS} pathname={pathname} />
        </li>
        <li>
          <Dropdown label="Reference" items={REFERENCE} pathname={pathname} />
        </li>
        <li>
          <Link
            href="/manifesto"
            className={`nav-pill${pathname === "/manifesto" ? " active" : ""}`}
          >
            Manifesto
          </Link>
        </li>
      </ul>
    </nav>
  );
}
