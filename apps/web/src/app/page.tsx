export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 py-16 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      <section className="w-full max-w-2xl space-y-6 rounded-2xl bg-white p-8 shadow-sm ring-1 ring-zinc-200 sm:p-12 dark:bg-zinc-900 dark:ring-zinc-800">
        <p className="text-sm font-medium tracking-[0.2em] text-zinc-500 uppercase">
          Frontend foundation
        </p>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          PrivaStream
        </h1>
        <p className="text-lg leading-8 text-zinc-600 dark:text-zinc-300">
          A privacy-first media pipeline for protecting faces, plates, sensitive
          text, and speech before content reaches its audience.
        </p>
        <p className="leading-7 text-zinc-600 dark:text-zinc-300">
          The creator console, media transport, detectors, and redaction pipeline
          are planned; this page is the current browser foundation.
        </p>
      </section>
    </main>
  );
}
