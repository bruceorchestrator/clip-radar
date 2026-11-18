"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

const ICON = "size-5";

const ITEMS = [
  {
    href: "/",
    label: "Radar",
    match: (p: string) => p === "/",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={ICON} aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="4" />
        <path d="M12 12l6-6" />
      </svg>
    ),
  },
  {
    href: "/clip",
    label: "Create",
    match: (p: string) => p.startsWith("/clip") || p.startsWith("/jobs"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={ICON} aria-hidden>
        <path d="M6 3l4 9-4 9M14 3l4 9-4 9" />
      </svg>
    ),
  },
  {
    href: "/autopilot",
    label: "Autopilot",
    match: (p: string) => p.startsWith("/autopilot"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={ICON} aria-hidden>
        <path d="M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z" />
      </svg>
    ),
  },
  {
    href: "/campaigns",
    label: "Campaigns",
    match: (p: string) => p.startsWith("/campaigns"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={ICON} aria-hidden>
        <path d="M12 2v20M17 6H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
      </svg>
    ),
  },
];

function Rail({ pathname }: { pathname: string | null }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 flex justify-around gap-1 border-t border-line bg-panel p-1.5 md:sticky md:top-0 md:h-screen md:w-[76px] md:flex-col md:justify-start md:border-r md:border-t-0 md:px-2 md:py-3.5"
    >
      <Link
        href="/"
        aria-label="Clip Radar home"
        className="mb-3.5 hidden size-10 place-items-center self-center rounded-xl bg-accent font-display text-lg font-bold text-accent-ink md:grid"
      >
        C
      </Link>
      {ITEMS.map((item) => {
        const active = pathname !== null && item.match(pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex min-w-14 flex-col items-center gap-1 rounded-xl px-1 py-2 text-[10.5px] md:w-[60px] ${
              active ? "bg-panel-2 text-fg ring-1 ring-line ring-inset [&_svg]:text-accent" : "text-muted hover:bg-panel-2 hover:text-fg"
            }`}
          >
            {item.icon}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function ActiveRail() {
  return <Rail pathname={usePathname()} />;
}

/** Icon rail on the left (bottom bar on phones), as in the approved panel mockup.
 *  The current path is runtime data, so the highlighted item streams in under Suspense. */
export function SideRail() {
  return (
    <Suspense fallback={<Rail pathname={null} />}>
      <ActiveRail />
    </Suspense>
  );
}
