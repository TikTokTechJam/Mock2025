"use client";

import { useEffect, useRef, useState } from "react";

import {
  BrowserMediaSession,
  MAX_PENDING_VIDEO_FRAMES,
  type BrowserMediaSessionState,
  type MediaFrameSnapshot,
} from "../lib/browser-media-session";

const STATE_LABELS: Record<BrowserMediaSessionState, string> = {
  idle: "Idle",
  starting: "Starting",
  live: "Live",
  stopping: "Stopping",
  error: "Error",
};

export default function Home() {
  const sourceVideoRef = useRef<HTMLVideoElement>(null);
  const outputVideoRef = useRef<HTMLVideoElement>(null);
  const sessionRef = useRef<BrowserMediaSession | null>(null);
  const [state, setState] = useState<BrowserMediaSessionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState<MediaFrameSnapshot | null>(null);

  useEffect(() => {
    return () => {
      sessionRef.current?.stop();
    };
  }, []);

  const stopSession = () => {
    setState("stopping");
    sessionRef.current?.stop();
    sessionRef.current = null;
    if (sourceVideoRef.current) {
      sourceVideoRef.current.srcObject = null;
    }
    if (outputVideoRef.current) {
      outputVideoRef.current.srcObject = null;
    }
    setFrame(null);
    setState("idle");
  };

  const startSession = async () => {
    if (state === "starting" || state === "live") {
      return;
    }

    setError(null);
    setFrame(null);
    setState("starting");
    let activeSession: BrowserMediaSession | null = null;
    activeSession = new BrowserMediaSession({
      onError: (message) => {
        if (sessionRef.current === activeSession) {
          setError(message);
          setState("error");
        }
      },
      onFrame: setFrame,
    });
    sessionRef.current = activeSession;

    try {
      const result = await activeSession.start();
      if (sourceVideoRef.current) {
        sourceVideoRef.current.srcObject = result.captureStream;
        sourceVideoRef.current.muted = true;
        await sourceVideoRef.current.play();
      }
      if (outputVideoRef.current) {
        outputVideoRef.current.srcObject = result.processedStream;
        await outputVideoRef.current.play().catch(() => undefined);
      }
      setState("live");
    } catch (caughtError) {
      activeSession.stop();
      if (sessionRef.current === activeSession) {
        sessionRef.current = null;
      }
      setError(caughtError instanceof Error ? caughtError.message : "Unable to start the media session.");
      setState("error");
    }
  };

  const isBusy = state === "starting" || state === "stopping";

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-50 sm:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="max-w-3xl space-y-4">
          <p className="text-sm font-medium tracking-[0.2em] text-cyan-300 uppercase">Browser media path</p>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">PrivaStream</h1>
          <p className="text-lg leading-8 text-zinc-300">
            A local WebRTC loopback that captures camera and microphone input, applies deterministic mock
            privacy processing, and publishes only the processed stream to the protected preview.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-6 rounded-2xl bg-zinc-900 p-6 ring-1 ring-zinc-800">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm text-zinc-400">Session status</p>
                <p className="mt-1 text-2xl font-semibold">{STATE_LABELS[state]}</p>
              </div>
              <div className="flex gap-3">
                <button
                  className="rounded-full bg-cyan-300 px-5 py-2.5 font-semibold text-zinc-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isBusy || state === "live"}
                  onClick={() => void startSession()}
                  type="button"
                >
                  Start session
                </button>
                <button
                  className="rounded-full border border-zinc-600 px-5 py-2.5 font-semibold text-zinc-100 transition hover:border-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isBusy || state === "idle"}
                  onClick={stopSession}
                  type="button"
                >
                  Stop
                </button>
              </div>
            </div>

            {error ? (
              <p className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200" role="alert">
                {error}
              </p>
            ) : null}

            <div className="grid gap-5 md:grid-cols-2">
              <figure className="space-y-2">
                <figcaption className="text-sm font-medium text-zinc-300">Local capture (not published)</figcaption>
                <video
                  className="aspect-video w-full rounded-xl bg-zinc-950 object-cover"
                  muted
                  playsInline
                  ref={sourceVideoRef}
                />
              </figure>
              <figure className="space-y-2">
                <figcaption className="text-sm font-medium text-cyan-200">Protected preview</figcaption>
                <video
                  className="aspect-video w-full rounded-xl bg-zinc-950 object-cover ring-1 ring-cyan-400/50"
                  controls
                  playsInline
                  ref={outputVideoRef}
                />
              </figure>
            </div>
          </div>

          <aside className="space-y-5 rounded-2xl bg-zinc-900 p-6 ring-1 ring-zinc-800">
            <div>
              <p className="text-sm font-medium tracking-[0.15em] text-zinc-400 uppercase">Mock processors</p>
              <dl className="mt-4 space-y-4 text-sm">
                <div>
                  <dt className="font-medium text-zinc-200">Video</dt>
                  <dd className="mt-1 text-zinc-400">A fixed center region is filled with a red MOCK REDACTION label.</dd>
                </div>
                <div>
                  <dt className="font-medium text-zinc-200">Audio</dt>
                  <dd className="mt-1 text-zinc-400">The gain transform mutes a deterministic 500 ms interval every 2 seconds.</dd>
                </div>
                <div>
                  <dt className="font-medium text-zinc-200">Backpressure</dt>
                  <dd className="mt-1 text-zinc-400">The video processor keeps at most {MAX_PENDING_VIDEO_FRAMES} animation frame pending.</dd>
                </div>
              </dl>
            </div>

            <div className="border-t border-zinc-800 pt-5 text-sm">
              <p className="font-medium text-zinc-200">Source timing</p>
              <p className="mt-1 text-zinc-400">
                {frame ? `${frame.sourceTimestampMs} ms from the capture epoch` : "Available after the session starts"}
              </p>
            </div>

            <p className="text-xs leading-5 text-zinc-500">
              This demo stays in the browser. Camera and microphone permissions are required; disconnects and
              processor errors stop the output instead of publishing the raw stream.
            </p>
          </aside>
        </section>
      </div>
    </main>
  );
}
