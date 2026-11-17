import { ApiStatus } from "@/components/api-status";

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-hairline">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-[0.8125rem] text-ink-low sm:px-6">
        <p>Every file you export is marked as AI generated. Your pages stay on this app.</p>
        <ApiStatus />
      </div>
    </footer>
  );
}
