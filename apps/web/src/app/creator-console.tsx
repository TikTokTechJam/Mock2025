"use client";

import { useEffect, useState, type ReactNode } from "react";

import {
  createMockCreatorConsoleClients,
  type CapabilityReadiness,
  type CreatorConsoleClients,
  type EnrollmentSnapshot,
  type ProtectedStreamHandle,
  type SafetySnapshot,
  type UnprotectedSourceHandle,
} from "../lib/creator-console-clients";

type ConsoleState = "idle" | "connecting" | "processing" | "protected" | "degraded" | "blocked" | "panic" | "stopped" | "error";
type PermissionState = "unknown" | "granted" | "blocked";

const SESSION_LABELS: Record<ConsoleState, string> = {
  idle: "Ready to configure",
  connecting: "Connecting",
  processing: "Processing",
  protected: "Protected preview",
  degraded: "Degraded protection",
  blocked: "Publication blocked",
  panic: "Panic stop active",
  stopped: "Session stopped",
  error: "Session error",
};

const SESSION_TONES: Record<ConsoleState, string> = {
  idle: "border-zinc-700 bg-zinc-800 text-zinc-200",
  connecting: "border-sky-400/40 bg-sky-400/10 text-sky-200",
  processing: "border-violet-400/40 bg-violet-400/10 text-violet-200",
  protected: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  degraded: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  blocked: "border-red-400/40 bg-red-400/10 text-red-200",
  panic: "border-red-400/40 bg-red-400/10 text-red-200",
  stopped: "border-zinc-700 bg-zinc-800 text-zinc-300",
  error: "border-red-400/40 bg-red-400/10 text-red-200",
};

const CAPABILITY_STATE_LABELS = {
  ready: "Ready",
  processing: "Processing",
  unavailable: "Unavailable",
} as const;

function StatusPill({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${className}`}>{children}</span>;
}

function SourcePreview({ source }: { source: UnprotectedSourceHandle | null }) {
  return (
    <div className="rounded-2xl border border-amber-400/30 bg-amber-400/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-amber-100">Unprotected source preview</p>
          <p className="mt-1 text-xs text-amber-200/70">Local device feedback only; never a publication fallback.</p>
        </div>
        <StatusPill className="border-amber-400/40 bg-amber-400/10 text-amber-200">Source</StatusPill>
      </div>
      <div className="mt-4 flex aspect-video items-center justify-center rounded-xl bg-zinc-950 text-center text-sm text-zinc-500">
        {source ? source.label : "No source selected"}
      </div>
    </div>
  );
}

function ProtectedPreview({ stream }: { stream: ProtectedStreamHandle | null }) {
  return (
    <div className="rounded-2xl border border-emerald-400/40 bg-emerald-400/5 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-emerald-100">Protected output</p>
          <p className="mt-1 text-xs text-emerald-200/70">Only a protected stream handle can enter this component.</p>
        </div>
        <StatusPill className="border-emerald-400/40 bg-emerald-400/10 text-emerald-200">Protected</StatusPill>
      </div>
      <div className="relative mt-4 flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-zinc-950 text-center text-sm text-zinc-400">
        {stream ? (
          <>
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_35%_35%,rgba(16,185,129,0.16),transparent_34%),radial-gradient(circle_at_70%_65%,rgba(6,182,212,0.12),transparent_36%)]" />
            <div className="relative space-y-2">
              <p className="font-semibold text-emerald-200">{stream.label}</p>
              <p className="text-xs text-zinc-500">{stream.redactions.join(" · ")}</p>
            </div>
          </>
        ) : (
          "Protected output is held until readiness allows publication"
        )}
      </div>
    </div>
  );
}

function CapabilityRow({ capability, onToggle }: { capability: CapabilityReadiness; onToggle: (enabled: boolean) => void }) {
  const stateClass = capability.state === "ready"
    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
    : capability.state === "processing"
      ? "border-violet-400/30 bg-violet-400/10 text-violet-200"
      : "border-red-400/30 bg-red-400/10 text-red-200";

  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-950/50 p-3 transition hover:border-zinc-700">
      <input
        checked={capability.enabled}
        className="mt-1 size-4 accent-cyan-300"
        onChange={(event) => onToggle(event.target.checked)}
        type="checkbox"
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-zinc-100">{capability.label}</span>
          {capability.required ? <StatusPill className="border-zinc-700 bg-zinc-800 text-zinc-400">Required</StatusPill> : null}
          <StatusPill className={stateClass}>{CAPABILITY_STATE_LABELS[capability.state]}</StatusPill>
        </span>
        <span className="mt-1 block text-xs leading-5 text-zinc-500">{capability.detail}</span>
      </span>
    </label>
  );
}

function EnrollmentPanel({
  consent,
  enrollment,
  onCapture,
  onConsentChange,
  onRemove,
}: {
  consent: boolean;
  enrollment: EnrollmentSnapshot;
  onCapture: () => void;
  onConsentChange: (consent: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <section className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-zinc-100">Creator enrollment</p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">Consent, status, replacement, and deletion are represented by a typed mock façade.</p>
        </div>
        <StatusPill className={enrollment.state === "ready" ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : enrollment.state === "capturing" ? "border-violet-400/30 bg-violet-400/10 text-violet-200" : "border-zinc-700 bg-zinc-800 text-zinc-400"}>
          {enrollment.state === "ready" ? "Ready" : enrollment.state === "capturing" ? "Capturing" : "Not enrolled"}
        </StatusPill>
      </div>
      <p className="text-sm leading-6 text-zinc-400">{enrollment.detail}</p>
      <label className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-950/50 p-3 text-xs leading-5 text-zinc-400">
        <input checked={consent} className="mt-1 size-4 accent-cyan-300" onChange={(event) => onConsentChange(event.target.checked)} type="checkbox" />
        <span>I consent to the mock creator-enrollment flow. No raw image or embedding is displayed by this console.</span>
      </label>
      <div className="flex flex-wrap gap-3">
        <button className="rounded-full bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40" disabled={!consent} onClick={onCapture} type="button">
          {enrollment.state === "ready" ? "Replace enrollment" : enrollment.state === "capturing" ? "Confirm mock capture" : "Capture enrollment"}
        </button>
        <button className="rounded-full border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-40" disabled={enrollment.state !== "ready"} onClick={onRemove} type="button">
          Delete enrollment
        </button>
      </div>
    </section>
  );
}

function ReadinessPanel({ capabilities, onToggle }: { capabilities: CapabilityReadiness[]; onToggle: (id: CapabilityReadiness["id"], enabled: boolean) => void }) {
  return (
    <section className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-zinc-100">Privacy capabilities</p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">Readiness is supplied by the mock client, not inferred from toggle state.</p>
        </div>
        <StatusPill className="border-sky-400/30 bg-sky-400/10 text-sky-200">Mock readiness</StatusPill>
      </div>
      <div className="space-y-2">
        {capabilities.map((capability) => (
          <CapabilityRow key={capability.id} capability={capability} onToggle={(enabled) => onToggle(capability.id, enabled)} />
        ))}
      </div>
    </section>
  );
}

export default function CreatorConsole() {
  const [clients] = useState<CreatorConsoleClients>(() => createMockCreatorConsoleClients());
  const [consoleState, setConsoleState] = useState<ConsoleState>("idle");
  const [permission, setPermission] = useState<PermissionState>("unknown");
  const [cameraId, setCameraId] = useState("mock-camera");
  const [microphoneId, setMicrophoneId] = useState("mock-microphone");
  const [policyId, setPolicyId] = useState("balanced-mock-policy");
  const [consent, setConsent] = useState(false);
  const [capabilities, setCapabilities] = useState<CapabilityReadiness[]>(clients.readiness.getSnapshot());
  const [enrollment, setEnrollment] = useState<EnrollmentSnapshot>(clients.enrollment.getSnapshot());
  const [safety, setSafety] = useState<SafetySnapshot>(clients.safety.getSnapshot());
  const [source, setSource] = useState<UnprotectedSourceHandle | null>(null);
  const [protectedStream, setProtectedStream] = useState<ProtectedStreamHandle | null>(null);

  useEffect(() => {
    const unsubscribeReadiness = clients.readiness.subscribe(setCapabilities);
    const unsubscribeEnrollment = clients.enrollment.subscribe(setEnrollment);
    const unsubscribeSafety = clients.safety.subscribe(setSafety);
    return () => {
      unsubscribeReadiness();
      unsubscribeEnrollment();
      unsubscribeSafety();
      clients.media.stop();
    };
  }, [clients]);

  const requiredUnavailable = capabilities.some((capability) => capability.enabled && capability.required && capability.state !== "ready");
  const optionalUnavailable = capabilities.some((capability) => capability.enabled && !capability.required && capability.state !== "ready");
  const canStart = permission === "granted" && !requiredUnavailable && safety.state !== "panic";

  const requestPermission = () => setPermission("granted");

  const startSession = async () => {
    if (permission !== "granted") {
      setPermission("blocked");
      setConsoleState("error");
      return;
    }
    if (safety.state === "panic") {
      setConsoleState("panic");
      return;
    }
    if (requiredUnavailable) {
      clients.media.stop();
      setSource(null);
      setProtectedStream(null);
      setConsoleState("blocked");
      return;
    }

    setConsoleState("connecting");
    setConsoleState("processing");
    try {
      const result = await clients.media.start({ cameraId, microphoneId, privacyPolicyId: policyId });
      setSource(result.sourceStream);
      setProtectedStream(result.protectedStream);
      setConsoleState(optionalUnavailable ? "degraded" : "protected");
    } catch {
      clients.media.stop();
      setSource(null);
      setProtectedStream(null);
      setConsoleState("error");
    }
  };

  const stopSession = () => {
    clients.media.stop();
    setProtectedStream(null);
    setSource(null);
    setConsoleState("stopped");
  };

  const triggerPanic = () => {
    clients.safety.triggerPanic();
    clients.media.stop();
    setProtectedStream(null);
    setConsoleState("panic");
  };

  const resetConsole = () => {
    clients.safety.clear();
    clients.readiness.reset();
    clients.enrollment.remove();
    clients.media.stop();
    setSource(null);
    setProtectedStream(null);
    setPermission("unknown");
    setConsent(false);
    setConsoleState("idle");
  };

  const showDemoState = (nextState: ConsoleState) => {
    if (nextState === "degraded") {
      clients.readiness.setState("visual_pii", "unavailable", "Mock visual text protection is unavailable; output is degraded.");
      setConsoleState("degraded");
      return;
    }
    if (nextState === "blocked") {
      clients.readiness.setState("spoken_pii", "unavailable", "Required spoken-PII protection is unavailable; output is held.");
      clients.media.stop();
      setProtectedStream(null);
      setConsoleState("blocked");
      return;
    }
    if (nextState === "panic") {
      triggerPanic();
      return;
    }
    setConsoleState(nextState);
  };

  return (
    <main className="min-h-screen bg-zinc-950 px-5 py-8 text-zinc-50 sm:px-8 lg:px-10">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-7">
        <header className="flex flex-col gap-5 border-b border-zinc-800 pb-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <p className="text-xs font-semibold tracking-[0.22em] text-cyan-300 uppercase">Creator privacy console</p>
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Prepare protected output</h1>
            <p className="text-base leading-7 text-zinc-400">Configure a mock privacy policy, review capability readiness, and distinguish unprotected source feedback from the protected output path.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill className={SESSION_TONES[consoleState]}>{SESSION_LABELS[consoleState]}</StatusPill>
            <StatusPill className="border-zinc-700 bg-zinc-900 text-zinc-400">Typed mock clients</StatusPill>
          </div>
        </header>

        <section className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="space-y-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 sm:p-6">
            <div className="flex flex-col gap-5 border-b border-zinc-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Media session</p>
                <p className="mt-1 text-xs leading-5 text-zinc-500">The console uses a mock media-session client. Real device acquisition and transport remain owned by issue #21.</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button className="rounded-full bg-cyan-300 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40" disabled={!canStart} onClick={() => void startSession()} type="button">Start protected session</button>
                <button className="rounded-full border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500" disabled={!source && consoleState !== "protected" && consoleState !== "degraded"} onClick={stopSession} type="button">Stop session</button>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <label className="space-y-2 text-sm text-zinc-300">
                <span className="block font-medium">Camera</span>
                <select className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-cyan-300" onChange={(event) => setCameraId(event.target.value)} value={cameraId}>
                  <option value="mock-camera">Mock camera</option>
                  <option value="mock-camera-2">Mock camera 2</option>
                </select>
              </label>
              <label className="space-y-2 text-sm text-zinc-300">
                <span className="block font-medium">Microphone</span>
                <select className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-cyan-300" onChange={(event) => setMicrophoneId(event.target.value)} value={microphoneId}>
                  <option value="mock-microphone">Mock microphone</option>
                  <option value="mock-microphone-2">Mock microphone 2</option>
                </select>
              </label>
              <label className="space-y-2 text-sm text-zinc-300">
                <span className="block font-medium">Privacy policy</span>
                <select className="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-cyan-300" onChange={(event) => setPolicyId(event.target.value)} value={policyId}>
                  <option value="balanced-mock-policy">Balanced mock policy</option>
                  <option value="strict-mock-policy">Strict mock policy</option>
                </select>
              </label>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
              <div>
                <p className="text-sm font-medium text-zinc-200">Permission state</p>
                <p className="mt-1 text-xs text-zinc-500">{permission === "granted" ? "Mock camera and microphone permission granted." : permission === "blocked" ? "Permission is required before starting." : "Permission has not been requested."}</p>
              </div>
              <button className="rounded-full border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500" onClick={requestPermission} type="button">{permission === "granted" ? "Permission granted" : "Request permission"}</button>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <SourcePreview source={source} />
              <ProtectedPreview stream={protectedStream} />
            </div>
          </div>

          <aside className="space-y-5 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 sm:p-6">
            <div>
              <p className="text-sm font-semibold text-zinc-100">Safety status</p>
              <div className="mt-3 flex items-center justify-between gap-3">
                <StatusPill className={safety.state === "normal" ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : "border-red-400/30 bg-red-400/10 text-red-200"}>{safety.state}</StatusPill>
                <button className="rounded-full border border-red-400/40 px-3 py-1.5 text-xs font-semibold text-red-200 transition hover:bg-red-400/10" onClick={triggerPanic} type="button">Panic stop</button>
              </div>
              <p className="mt-3 text-sm leading-6 text-zinc-400">{safety.detail}</p>
            </div>
            <div className="border-t border-zinc-800 pt-5">
              <p className="text-sm font-semibold text-zinc-100">Session handoff</p>
              <dl className="mt-3 space-y-3 text-sm">
                <div className="flex items-start justify-between gap-3"><dt className="text-zinc-500">Source</dt><dd className="text-right text-zinc-300">{source ? "Selected" : "Not selected"}</dd></div>
                <div className="flex items-start justify-between gap-3"><dt className="text-zinc-500">Protected output</dt><dd className="text-right text-zinc-300">{protectedStream ? "Available" : "Held"}</dd></div>
                <div className="flex items-start justify-between gap-3"><dt className="text-zinc-500">Required readiness</dt><dd className="text-right text-zinc-300">{requiredUnavailable ? "Blocking" : "Ready"}</dd></div>
              </dl>
            </div>
            <p className="text-xs leading-5 text-zinc-500">Readiness, enrollment, safety, and media values are deterministic local mock façades. They are not backend authorization or production privacy guarantees.</p>
            <div className="border-t border-zinc-800 pt-5">
              <p className="text-xs font-semibold tracking-[0.14em] text-zinc-500 uppercase">Render mock states</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(["connecting", "processing", "degraded", "blocked", "stopped", "error"] as const).map((demoState) => (
                  <button className="rounded-full border border-zinc-700 px-3 py-1.5 text-xs font-semibold text-zinc-300 transition hover:border-zinc-500" key={demoState} onClick={() => showDemoState(demoState)} type="button">
                    {demoState}
                  </button>
                ))}
              </div>
            </div>
            <button className="w-full rounded-full border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-300 transition hover:border-zinc-500" onClick={resetConsole} type="button">Reset console</button>
          </aside>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <EnrollmentPanel consent={consent} enrollment={enrollment} onCapture={() => clients.enrollment.capture()} onConsentChange={setConsent} onRemove={() => clients.enrollment.remove()} />
          <ReadinessPanel capabilities={capabilities} onToggle={(id, enabled) => clients.readiness.setEnabled(id, enabled)} />
        </section>
      </div>
    </main>
  );
}
