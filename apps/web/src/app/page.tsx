import Link from "next/link";

const STEPS = [
  "Photograph a page of your own writing and upload it.",
  "Add a card, letter or planner page and say what goes where.",
  "Check the preview, ask for changes, then export a PDF or PNG.",
];

export default function Home() {
  return (
    <main id="main" className="mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-6 lg:pt-16">
      <div className="grid items-start gap-12 lg:grid-cols-[1.15fr_1fr] lg:gap-16">
        <div>
          <h1 className="hand text-[length:var(--hand-xl)] text-ink">
            Your handwriting, on the cards you keep meaning to write.
          </h1>
          <svg
            aria-hidden="true"
            viewBox="0 0 240 14"
            className="mt-3 h-3.5 w-56 text-margin"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
          >
            <path d="M3 9c30-8 50 4 80-1s52-6 80-1 50 3 74-3" />
          </svg>
          <p className="mt-6 max-w-[34rem] text-[length:var(--text-lg)] text-ink-mid">
            Upload one page of your own writing. We learn how you form your letters, then write new
            words onto your files in that hand, with the small wobbles that mean no two lines look
            copied.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link href="/hand" className="btn btn-primary">
              Add a page of your handwriting
            </Link>
            <Link href="/chats" className="link text-[0.9375rem] font-semibold">
              Already set up? Open your chats
            </Link>
          </div>
          <ol className="mt-12 grid max-w-[34rem] gap-4 border-l-2 border-margin pl-5">
            {STEPS.map((s, i) => (
              <li key={s} className="flex gap-4 text-[0.9375rem] text-ink-mid">
                <span className="hand w-6 shrink-0 text-[1.75rem] leading-none text-pen" aria-hidden="true">
                  {i + 1}
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>

        <figure className="relative mx-auto w-full max-w-[28rem] lg:mt-4">
          <div
            className="sheet ruled relative -rotate-[1.2deg] min-h-[22rem] px-8 pb-10 pt-[26px]"
            aria-label="Example of a handwritten note"
          >
            <span aria-hidden="true" className="absolute inset-y-0 left-6 w-px bg-margin/70" />
            <p className="hand pl-4 text-[2.1rem] leading-[32px] text-pen">
              Dear Nan,
              <br />
              the scarf fits perfectly.
              <br />
              Come for tea on Sunday?
              <br />
              Love, Mina
            </p>
          </div>
          <figcaption className="mt-5 pl-2 text-[0.8125rem] text-ink-low">
            A sample note, set in a handwriting font. Yours will come from your own page.
          </figcaption>
        </figure>
      </div>
    </main>
  );
}
