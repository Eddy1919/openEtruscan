"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/normalizer", label: "Normalizer" },
  { href: "/explorer", label: "Explorer" },
  { href: "/stats", label: "Statistics" },
  { href: "/classifier", label: "Classifier" },
  { href: "/docs", label: "Docs" },
  { href: "/manifesto", label: "Manifesto" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="nav-bar">
      <Link href="/" className="nav-brand" style={{ textDecoration: "none" }}>
        <span style={{ color: "var(--text-primary)" }}>𐌏𐌐𐌄𐌍</span><span style={{ color: "var(--accent)" }}>Etruscan</span>
      </Link>
      <ul className="nav-pills">
        {NAV_ITEMS.map(({ href, label }) => (
          <li key={href}>
            <Link
              href={href}
              className={`nav-pill${pathname === href ? " active" : ""}`}
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
