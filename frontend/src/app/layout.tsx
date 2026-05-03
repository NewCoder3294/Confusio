import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { SystemFooter } from "@/components/system-footer";
import { NavLink } from "@/components/nav-link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Confusio — Operator Console",
  description:
    "Title 10 §1631 synthetic-deception toolchain. Operator console for INSCOM-aligned mission planning.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full overflow-hidden flex flex-col">
        <NavBar />
        <main className="flex-1 min-h-0 flex flex-col">{children}</main>
        <SystemFooter />
      </body>
    </html>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function NavBar() {
  return (
    <nav className="border-b border-border-subtle bg-bg-panel">
      <div className="mx-auto px-6 h-11 flex items-center justify-between">
        <div className="flex items-center gap-5">
          <Link
            href="/"
            className="flex items-center gap-2 group"
            aria-label="Confusio — Operator Console"
          >
            <span
              className="block w-[8px] h-[8px] bg-classified shrink-0"
              aria-hidden="true"
            />
            <span className="font-sans font-medium text-fg-default tracking-tight text-[15px]">
              Confusio
            </span>
          </Link>
          <span className="text-fg-faint text-[12px] font-mono uppercase tracking-[0.18em]">
            Operator&nbsp;Console
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          <NavLink href="/">Mission Board</NavLink>
          <NavLink href="/personas">Agents</NavLink>
          <NavLink href="/channels">Channels</NavLink>
          <NavLink href="/verify">Verify</NavLink>
          <NavLink href="/settings">Settings</NavLink>
        </div>
      </div>
    </nav>
  );
}


