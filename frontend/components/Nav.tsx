"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Navbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  NavbarMenuToggle,
  NavbarMenu,
  NavbarMenuItem,
  DropdownItem,
  DropdownTrigger,
  Dropdown,
  DropdownMenu,
  Button
} from "@nextui-org/react";

const PRIMARY = [
  { href: "/search", label: "Search" },
  { href: "/concordance", label: "Concordance" },
  { href: "/explorer", label: "Explorer" },
  { href: "/classifier", label: "Classifier" },
  { href: "/genetics", label: "Genetics" }
];

const TOOLS = [
  { href: "/normalizer", label: "Normalizer" },
  { href: "/lacunae", label: "Restore Lacunae" },
  { href: "/compare", label: "Compare" },
  { href: "/timeline", label: "Timeline" },
  { href: "/names", label: "Names" },
];

const REFERENCE = [
  { href: "/stats", label: "Statistics" },
  { href: "/downloads", label: "Downloads" },
  { href: "/docs", label: "Docs" },
];

export default function Nav() {
  const pathname = usePathname();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <Navbar 
      isBordered 
      isMenuOpen={isMenuOpen} 
      onMenuOpenChange={setIsMenuOpen}
      classNames={{
        base: "bg-background",
        wrapper: "px-4 sm:px-6 max-w-[1200px]",
        item: [
          "flex",
          "relative",
          "h-full",
          "items-center",
          "data-[active=true]:after:content-['']",
          "data-[active=true]:after:absolute",
          "data-[active=true]:after:bottom-0",
          "data-[active=true]:after:left-0",
          "data-[active=true]:after:right-0",
          "data-[active=true]:after:h-[2px]",
          "data-[active=true]:after:rounded-[2px]",
          "data-[active=true]:after:bg-primary",
        ]
      }}
    >
      <NavbarContent className="sm:hidden" justify="start">
        <NavbarMenuToggle aria-label={isMenuOpen ? "Close menu" : "Open menu"} />
      </NavbarContent>

      <NavbarContent className="sm:hidden lg:flex" justify="start">
        <NavbarBrand>
          <Link href="/" className="font-display font-bold text-xl flex items-center gap-1 group">
            <span className="text-foreground transition-colors group-hover:text-primary">𐌏𐌐𐌄𐌍</span>
            <span className="text-primary">Etruscan</span>
          </Link>
        </NavbarBrand>
      </NavbarContent>

      <NavbarContent className="hidden sm:flex gap-4" justify="center">
        {PRIMARY.map((item) => (
          <NavbarItem key={item.href} isActive={pathname === item.href}>
            <Link color="foreground" href={item.href} className={`text-sm font-medium transition-colors ${pathname === item.href ? 'text-primary' : 'text-foreground hover:text-primary'}`}>
              {item.label}
            </Link>
          </NavbarItem>
        ))}

        <Dropdown>
          <NavbarItem>
            <DropdownTrigger>
              <Button
                disableRipple
                className={`p-0 bg-transparent data-[hover=true]:bg-transparent text-sm font-medium transition-colors ${TOOLS.some(t => t.href === pathname) ? 'text-primary' : 'text-foreground hover:text-primary'}`}
                radius="sm"
                variant="light"
              >
                Tools
              </Button>
            </DropdownTrigger>
          </NavbarItem>
          <DropdownMenu
            aria-label="Tools features"
            className="w-[200px]"
            itemClasses={{
              base: "gap-4",
            }}
          >
            {TOOLS.map((item) => (
              <DropdownItem key={item.href} as={Link} href={item.href}>
                <span className={pathname === item.href ? 'text-primary' : ''}>
                  {item.label}
                </span>
              </DropdownItem>
            ))}
          </DropdownMenu>
        </Dropdown>

        <Dropdown>
          <NavbarItem>
            <DropdownTrigger>
              <Button
                disableRipple
                className={`p-0 bg-transparent data-[hover=true]:bg-transparent text-sm font-medium transition-colors ${REFERENCE.some(t => t.href === pathname) ? 'text-primary' : 'text-foreground hover:text-primary'}`}
                radius="sm"
                variant="light"
              >
                Reference
              </Button>
            </DropdownTrigger>
          </NavbarItem>
          <DropdownMenu
            aria-label="Reference features"
            className="w-[200px]"
          >
            {REFERENCE.map((item) => (
              <DropdownItem key={item.href} as={Link} href={item.href}>
                <span className={pathname === item.href ? 'text-primary' : ''}>
                  {item.label}
                </span>
              </DropdownItem>
            ))}
          </DropdownMenu>
        </Dropdown>

        <NavbarItem isActive={pathname === "/manifesto"}>
          <Link color="foreground" href="/manifesto" className={`text-sm font-medium transition-colors ${pathname === "/manifesto" ? 'text-primary' : 'text-foreground hover:text-primary'}`}>
            Manifesto
          </Link>
        </NavbarItem>
      </NavbarContent>

      {/* Mobile Menu */}
      <NavbarMenu className="bg-background/80 backdrop-blur-md pt-6">
        {[
          ...PRIMARY,
          ...TOOLS,
          ...REFERENCE,
          { href: "/manifesto", label: "Manifesto" }
        ].map((item, index) => (
          <NavbarMenuItem key={`${item.href}-${index}`} isActive={pathname === item.href}>
            <Link
              className={`w-full ${pathname === item.href ? 'text-primary font-bold' : 'text-foreground'}`}
              href={item.href}
              onClick={() => setIsMenuOpen(false)}
            >
              {item.label}
            </Link>
          </NavbarMenuItem>
        ))}
      </NavbarMenu>
    </Navbar>
  );
}
