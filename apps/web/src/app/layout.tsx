import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import "@fontsource-variable/hanken-grotesk";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";

// Caveat, SIL Open Font License 1.1 (see ./fonts/OFL.txt). Used for headings only.
const caveat = localFont({
  src: "./fonts/Caveat.ttf",
  variable: "--font-caveat",
  weight: "400 700",
  display: "swap",
});

export const metadata: Metadata = {
  title: "handwriting.ai: your hand, on any card",
  description:
    "Learn your handwriting from your own pages, then write new text onto cards, letters and planners in your hand.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={caveat.variable}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-sheet focus:px-4 focus:py-2"
        >
          Skip to content
        </a>
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
