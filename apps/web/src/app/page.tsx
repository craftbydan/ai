import { ApiStatus } from "@/components/api-status";

export default function Home() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-3xl font-semibold">handwriting-ai</h1>
      <p className="mt-3 text-stone-600">
        Learn your handwriting from your own pages, then write new text onto your files.
      </p>
      <div className="mt-8 rounded border border-stone-200 bg-white p-4">
        <ApiStatus />
      </div>
    </main>
  );
}
