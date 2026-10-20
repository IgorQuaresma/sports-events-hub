"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Icon from "./Icon";

const NAV = [
  { href: "/search", label: "All events" },
  { href: "/search?sport=triathlon", label: "Triathlon", sport: "triathlon" },
  { href: "/search?sport=running", label: "Running", sport: "running" },
  { href: "/search?sport=trail-running", label: "Trail", sport: "trail-running" },
  { href: "/search?sport=cycling", label: "Cycling", sport: "cycling" },
  { href: "/search?sport=hyrox", label: "HYROX", sport: "hyrox" },
];

function NavLinks({ onNavigate, vertical }: { onNavigate?: () => void; vertical?: boolean }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const sport = params.get("sport");
  return (
    <>
      {NAV.map((item) => {
        const active =
          pathname === "/search" && (item.sport ? sport === item.sport : !sport);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              active ? "bg-brand-50 text-brand-800" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
            } ${vertical ? "block" : ""}`}
          >
            {item.label}
          </Link>
        );
      })}
      <Link
        href="/sources"
        onClick={onNavigate}
        aria-current={pathname === "/sources" ? "page" : undefined}
        className={`rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 ${vertical ? "block" : ""} ${
          pathname === "/sources" ? "bg-brand-50 text-brand-800" : ""
        }`}
      >
        Data sources
      </Link>
    </>
  );
}

export default function SiteHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/75">
      <div className="container-page flex h-14 items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold text-slate-900" aria-label="Sports Events Hub — home">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white" aria-hidden>
            <Icon name="route" className="h-5 w-5" />
          </span>
          <span className="hidden sm:inline">Sports Events Hub</span>
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
          <Suspense fallback={null}>
            <NavLinks />
          </Suspense>
        </nav>
        <button
          type="button"
          className="btn-ghost px-2 lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? "x" : "menu"} className="h-5 w-5" />
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
        </button>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Main" className="border-t border-slate-200 bg-white lg:hidden">
          <div className="container-page grid gap-1 py-3">
            <Suspense fallback={null}>
              <NavLinks vertical onNavigate={() => setOpen(false)} />
            </Suspense>
          </div>
        </nav>
      )}
    </header>
  );
}
