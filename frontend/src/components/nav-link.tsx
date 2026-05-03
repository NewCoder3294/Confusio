"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function NavLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  // Active when exact match, or when href is a non-root prefix of pathname
  const isActive =
    pathname === href || (href !== "/" && pathname?.startsWith(href + "/"));

  return (
    <Link
      href={href}
      className={`px-3 py-1 text-[12px] uppercase tracking-[0.14em] transition-colors ${
        isActive
          ? "text-fg-default bg-bg-elevated border-b-[2px] border-info-fg -mb-[1px]"
          : "text-fg-muted hover:text-fg-default hover:bg-bg-hover border-b-[2px] border-transparent -mb-[1px]"
      }`}
    >
      {children}
    </Link>
  );
}
