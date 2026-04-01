"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/architecture", label: "Architecture" },
];

export function NavHeader() {
  const pathname = usePathname();

  return (
    <header className="border-b border-border/40 px-6 py-3 shrink-0">
      <div className="max-w-5xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded bg-primary/15 flex items-center justify-center">
              <span className="text-primary font-semibold text-xs">S</span>
            </div>
            <h1 className="font-heading text-lg tracking-tight">SecSignal</h1>
          </Link>
          <nav className="flex items-center gap-4">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`text-xs transition-colors ${
                  pathname === link.href
                    ? "text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground/70"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <span className="text-[11px] text-muted-foreground/60 tracking-wide uppercase">
          SEC Intelligence
        </span>
      </div>
    </header>
  );
}
