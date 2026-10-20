import type { Metadata, Viewport } from "next";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Sports Events Hub — find your next race", template: "%s · Sports Events Hub" },
  description:
    "Find triathlons, runs, trail races, cycling, open-water swims, OCR and HYROX events — with registration status, prices and a direct link to the official sign-up.",
  applicationName: "Sports Events Hub",
};

export const viewport: Viewport = { themeColor: "#136f94", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:shadow-lift"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" tabIndex={-1} className="container-page flex-1 py-6 focus:outline-none sm:py-8">
          {children}
        </main>
        <footer className="mt-12 border-t border-slate-200 bg-white">
          <div className="container-page grid gap-6 py-8 text-sm text-slate-600 sm:grid-cols-[2fr_1fr_1fr]">
            <div className="space-y-2">
              <p className="font-semibold text-slate-900">Sports Events Hub</p>
              <p>
                We collect race data from federations, open APIs and organizer websites. Registration and payment
                always happen on the organizer&apos;s official site — never here.
              </p>
            </div>
            <div className="space-y-2">
              <p className="font-semibold text-slate-900">Explore</p>
              <ul className="space-y-1">
                <li><Link href="/search?reg_state=open&sort=date" className="hover:text-brand-700 hover:underline">Registration open</Link></li>
                <li><Link href="/search?sort=date" className="hover:text-brand-700 hover:underline">Upcoming events</Link></li>
              </ul>
            </div>
            <div className="space-y-2">
              <p className="font-semibold text-slate-900">About</p>
              <ul className="space-y-1">
                <li><Link href="/sources" className="hover:text-brand-700 hover:underline">Data sources &amp; attribution</Link></li>
                <li><Link href="/legal" className="hover:text-brand-700 hover:underline">Impressum &amp; privacy</Link></li>
              </ul>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
