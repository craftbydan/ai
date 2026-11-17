import Link from "next/link";

const NAV = [
  { href: "/hand", label: "Your hand" },
  { href: "/chats", label: "Chats" },
];

export function SiteHeader() {
  return (
    <header className="border-b border-hairline">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="hand text-[2rem] leading-none text-ink">
          handwriting<span className="text-margin">.</span>ai
        </Link>
        <nav aria-label="Main">
          <ul className="flex gap-1">
            {NAV.map((n) => (
              <li key={n.href}>
                <Link
                  href={n.href}
                  className="inline-flex min-h-[44px] items-center rounded-control px-3 text-[0.9375rem] font-semibold text-ink-mid hover:bg-paper-well hover:text-ink"
                >
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
