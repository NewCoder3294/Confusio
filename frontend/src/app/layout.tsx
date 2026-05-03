import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { SystemFooter } from "@/components/system-footer";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mendacity — Operator Console",
  description:
    "Title 10 §1631 synthetic-deception toolchain. Operator console for INSCOM-aligned mission planning.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ClassificationBanner />
        <NavBar />
        <main className="flex-1 flex flex-col">{children}</main>
        <SystemFooter />
      </body>
    </html>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function ClassificationBanner() {
  return (
    <div
      role="banner"
      className="bg-classified text-white text-[11px] font-mono uppercase tracking-[0.18em] py-1 text-center select-none"
    >
      SANDBOX // TITLE 10 §1631 // FOREIGN ACTORS ONLY // OPERATOR EYES
    </div>
  );
}

function NavBar() {
  return (
    <nav className="border-b border-border-subtle bg-bg-panel">
      <div className="max-w-[1400px] mx-auto px-6 h-12 flex items-center justify-between">
        <div className="flex items-baseline gap-6">
          <Link href="/" className="font-mono text-fg-default tracking-wider text-sm">
            <span className="text-classified">/</span>MENDACITY
          </Link>
          <span className="text-fg-faint text-[11px] font-mono uppercase tracking-widest">
            Operator Console
          </span>
        </div>
        <div className="flex items-center gap-1">
          <NavLink href="/">Mission Board</NavLink>
          <NavLink href="/intel">Intel Inbox</NavLink>
          <NavLink href="/backstop">Backstop</NavLink>
          <NavLink href="/personas">Personas</NavLink>
          <NavLink href="/channels">Channels</NavLink>
          <NavLink href="/audit">Authorization &amp; Audit</NavLink>
          <NavLink href="/runbook">Runbook</NavLink>
        </div>
      </div>
    </nav>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-1 text-[12px] uppercase tracking-[0.14em] text-fg-muted hover:text-fg-default hover:bg-bg-hover transition-colors"
    >
      {children}
    </Link>
  );
}

