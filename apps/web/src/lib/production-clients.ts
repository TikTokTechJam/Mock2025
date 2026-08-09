import { BrowserMediaSession } from "./browser-media-session";
import type {
  CapabilityId,
  CapabilityReadiness,
  CreatorConsoleClients,
  EnrollmentClient,
  EnrollmentSnapshot,
  MediaSessionClientHandle,
  MediaSessionOutputHandle,
  ReadinessClient,
  SafetyClient,
  SafetySnapshot,
  UnprotectedSourceHandle,
  ProtectedStreamHandle,
} from "./creator-console-clients";
import type { MediaSessionClient, MediaSessionStartRequest } from "./media-session-client";

const DEFAULT_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const FACE_ENROLLMENT_PATH = "/privacy/face/enrollment";
const FACE_READINESS_PATH = "/privacy/face/readiness";

type FetchImplementation = typeof fetch;

interface FaceEnrollmentResponse {
  state?: string;
}

interface FaceReadinessResponse {
  capability?: string;
  enabled?: boolean;
  required?: boolean;
  ready?: boolean;
  reason_code?: string | null;
}

interface ProductionClientOptions {
  apiBaseUrl?: string;
  fetchImpl?: FetchImplementation;
}

function apiUrl(apiBaseUrl: string, path: string): string {
  return `${apiBaseUrl.replace(/\/$/, "")}${path}`;
}

function responseDetail(status: number, operation: string): string {
  switch (status) {
    case 400:
      return "The request was rejected by the privacy API.";
    case 404:
      return "The requested privacy resource was not found.";
    case 409:
      return "The privacy resource already exists.";
    case 413:
      return "The enrollment sample is larger than the configured limit.";
    case 422:
      return "The privacy API could not accept the supplied enrollment sample.";
    case 503:
      return `The privacy ${operation} capability is unavailable.`;
    default:
      return `The privacy ${operation} request failed.`;
  }
}

function networkDetail(operation: string): string {
  return `The privacy ${operation} API could not be reached.`;
}

function safeErrorDetail(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.startsWith("The ") ? error.message : fallback;
}

function createListeners<T>(): {
  listeners: Set<(snapshot: T) => void>;
  notify: (snapshot: T) => void;
} {
  const listeners = new Set<(snapshot: T) => void>();
  return {
    listeners,
    notify: (snapshot) => listeners.forEach((listener) => listener(snapshot)),
  };
}

function enrollmentSnapshotFromState(state: string | undefined): EnrollmentSnapshot {
  switch (state) {
    case "enrolled":
      return {
        detail: "Creator enrollment is ready; ambiguous matches remain protected.",
        state: "ready",
      };
    case "not_enrolled":
      return {
        detail: "No creator identity is enrolled. All detected faces remain protected.",
        state: "not_enrolled",
      };
    case "enrolling":
    case "replacing":
    case "deleting":
      return {
        detail: "The production enrollment operation is in progress.",
        state: "capturing",
      };
    default:
      return {
        detail: "The production enrollment state could not be established.",
        state: "error",
      };
  }
}

function reasonDetail(reasonCode: string | null | undefined, fallback: string): string {
  if (!reasonCode) {
    return fallback;
  }

  const labels: Record<string, string> = {
    detector_unavailable: "The configured privacy detector is unavailable.",
    detector_error: "The configured privacy detector reported an error.",
    enrollment_missing: "Creator enrollment is required before protected publication.",
    authorization_unavailable: "Privacy control authorization is unavailable.",
    safety_unavailable: "Server safety status is unavailable.",
    panic_active: "Panic is active. Protected publication is blocked.",
  };
  return labels[reasonCode] ?? fallback;
}

async function captureEnrollmentImage(sourceStream: MediaStream): Promise<Blob> {
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.srcObject = sourceStream;

  try {
    await video.play();
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      await new Promise<void>((resolve, reject) => {
        let timeout = 0;
        const onReady = () => {
          cleanup();
          resolve();
        };
        const onError = () => {
          cleanup();
          reject(new Error("The active camera frame could not be decoded."));
        };
        const cleanup = () => {
          window.clearTimeout(timeout);
          video.removeEventListener("loadeddata", onReady);
          video.removeEventListener("error", onError);
        };
        timeout = window.setTimeout(() => {
          cleanup();
          reject(new Error("The active camera did not provide a usable frame."));
        }, 5_000);
        video.addEventListener("loadeddata", onReady, { once: true });
        video.addEventListener("error", onError, { once: true });
      });
    }
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      throw new Error("The active camera did not provide a usable frame.");
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("The browser could not capture an enrollment frame.");
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("The browser could not encode an enrollment frame."));
        }
      }, "image/jpeg", 0.85);
    });
  } finally {
    video.pause();
    video.srcObject = null;
  }
}

export class ProductionEnrollmentClient implements EnrollmentClient {
  private snapshotValue: EnrollmentSnapshot = {
    detail: "Waiting for the production enrollment API.",
    state: "error",
  };
  private readonly listeners = createListeners<EnrollmentSnapshot>();
  private readonly apiBaseUrl: string;
  private readonly fetchImpl: FetchImplementation;

  public constructor(options: ProductionClientOptions = {}) {
    this.apiBaseUrl = options.apiBaseUrl ?? DEFAULT_API_BASE_URL;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  public getSnapshot(): EnrollmentSnapshot {
    return this.snapshotValue;
  }

  public subscribe(listener: (snapshot: EnrollmentSnapshot) => void): () => void {
    this.listeners.listeners.add(listener);
    return () => this.listeners.listeners.delete(listener);
  }

  public async refresh(): Promise<void> {
    try {
      const response = await this.fetchImpl(apiUrl(this.apiBaseUrl, FACE_ENROLLMENT_PATH), {
        method: "GET",
        credentials: "include",
      });
      if (!response.ok) {
        if (response.status === 404) {
          this.update({
            detail: "No creator identity is enrolled. All detected faces remain protected.",
            state: "not_enrolled",
          });
          return;
        }
        throw new Error(responseDetail(response.status, "enrollment"));
      }
      const body = (await response.json()) as FaceEnrollmentResponse;
      this.update(enrollmentSnapshotFromState(body.state));
    } catch (error) {
      this.update({ detail: safeErrorDetail(error, networkDetail("enrollment")), state: "error" });
    }
  }

  public async capture(sourceStream: MediaStream | null, consent: boolean): Promise<void> {
    if (!consent) {
      this.update({ detail: "Explicit creator consent is required for enrollment.", state: "error" });
      return;
    }
    if (!sourceStream) {
      this.update({ detail: "Start a camera session before capturing enrollment.", state: "error" });
      return;
    }

    this.update({ detail: "Capturing one bounded enrollment frame from the active source.", state: "capturing" });
    try {
      const image = await captureEnrollmentImage(sourceStream);
      const form = new FormData();
      form.append("images", image, "enrollment.jpg");
      form.append("consent", "true");
      const method = this.snapshotValue.state === "ready" ? "PUT" : "POST";
      const response = await this.fetchImpl(apiUrl(this.apiBaseUrl, FACE_ENROLLMENT_PATH), {
        method,
        body: form,
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(responseDetail(response.status, "enrollment"));
      }
      const body = (await response.json()) as FaceEnrollmentResponse;
      this.update(enrollmentSnapshotFromState(body.state));
    } catch (error) {
      this.update({ detail: safeErrorDetail(error, networkDetail("enrollment")), state: "error" });
    }
  }

  public async remove(): Promise<void> {
    try {
      const response = await this.fetchImpl(apiUrl(this.apiBaseUrl, FACE_ENROLLMENT_PATH), {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok && response.status !== 404) {
        throw new Error(responseDetail(response.status, "enrollment"));
      }
      this.update({
        detail: "Enrollment removed. All detected faces remain protected.",
        state: "not_enrolled",
      });
    } catch (error) {
      this.update({ detail: safeErrorDetail(error, networkDetail("enrollment deletion")), state: "error" });
    }
  }

  private update(snapshot: EnrollmentSnapshot): void {
    this.snapshotValue = snapshot;
    this.listeners.notify(snapshot);
  }
}

const CAPABILITY_DETAILS: Record<CapabilityId, { label: string; required: boolean }> = {
  face: { label: "Bystander faces", required: true },
  license_plate: { label: "License plates", required: true },
  visual_pii: { label: "Visual text PII", required: false },
  spoken_pii: { label: "Spoken PII", required: true },
};

function unavailableCapabilities(detail: string): CapabilityReadiness[] {
  return (Object.keys(CAPABILITY_DETAILS) as CapabilityId[]).map((id) => ({
    id,
    label: CAPABILITY_DETAILS[id].label,
    detail,
    enabled: true,
    required: CAPABILITY_DETAILS[id].required,
    state: "unavailable",
  }));
}

export class ProductionReadinessClient implements ReadinessClient {
  private snapshotValue = unavailableCapabilities("Waiting for server capability readiness.");
  private readonly listeners = createListeners<CapabilityReadiness[]>();
  private readonly apiBaseUrl: string;
  private readonly fetchImpl: FetchImplementation;

  public constructor(options: ProductionClientOptions = {}) {
    this.apiBaseUrl = options.apiBaseUrl ?? DEFAULT_API_BASE_URL;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  public getSnapshot(): CapabilityReadiness[] {
    return this.snapshotValue;
  }

  public subscribe(listener: (snapshot: CapabilityReadiness[]) => void): () => void {
    this.listeners.listeners.add(listener);
    return () => this.listeners.listeners.delete(listener);
  }

  public async refresh(): Promise<void> {
    try {
      const response = await this.fetchImpl(apiUrl(this.apiBaseUrl, FACE_READINESS_PATH), {
        method: "GET",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(responseDetail(response.status, "readiness"));
      }
      const body = (await response.json()) as FaceReadinessResponse;
      if (body.capability !== "face" || typeof body.ready !== "boolean") {
        throw new Error("The privacy readiness response was invalid.");
      }
      const faceDetail = reasonDetail(body.reason_code, body.ready ? "Face protection is ready." : "Face protection is not ready.");
      this.snapshotValue = [
        {
          id: "face",
          label: CAPABILITY_DETAILS.face.label,
          detail: faceDetail,
          enabled: body.enabled ?? true,
          required: body.required ?? true,
          state: body.ready ? "ready" : "unavailable",
        },
        ...unavailableCapabilities("This capability is not exposed by the current server readiness API.").filter((capability) => capability.id !== "face"),
      ];
      this.listeners.notify(this.snapshotValue);
    } catch (error) {
      this.snapshotValue = unavailableCapabilities(safeErrorDetail(error, networkDetail("readiness")));
      this.listeners.notify(this.snapshotValue);
    }
  }

  public setEnabled(id: CapabilityId, enabled: boolean): void {
    this.snapshotValue = this.snapshotValue.map((capability) => capability.id === id ? { ...capability, enabled } : capability);
    this.listeners.notify(this.snapshotValue);
  }

  public async reset(): Promise<void> {
    await this.refresh();
  }
}

export class ProductionMediaSessionClient implements MediaSessionClientHandle {
  private readonly browserClient: MediaSessionClient<MediaStream, MediaStream>;

  public constructor(browserClient: MediaSessionClient<MediaStream, MediaStream> = new BrowserMediaSession()) {
    this.browserClient = browserClient;
  }

  public async start(request: MediaSessionStartRequest): Promise<MediaSessionOutputHandle> {
    const output = await this.browserClient.start(request);
    const sourceStream: UnprotectedSourceHandle = {
      kind: "unprotected-source",
      label: "Camera + microphone source",
      stream: output.sourceStream,
    };
    const protectedStream: ProtectedStreamHandle = {
      kind: "protected-output",
      label: "Protected media output",
      redactions: ["bystander faces", "license plates", "supported spoken PII"],
      stream: output.protectedStream,
    };
    return { sourceStream, protectedStream };
  }

  public stop(): void {
    this.browserClient.stop();
  }
}

export interface SafetyEventTransport {
  getSnapshot(): SafetySnapshot;
  subscribe(listener: (snapshot: SafetySnapshot) => void): () => void;
  refresh(): Promise<void>;
  triggerPanic(): Promise<void>;
  clear(): Promise<void>;
}

export class ProductionSafetyClient implements SafetyClient {
  private snapshotValue: SafetySnapshot = {
    detail: "The #13 safety event transport is not connected; protected publication is blocked.",
    state: "blocked",
  };
  private readonly listeners = createListeners<SafetySnapshot>();
  private readonly onPanic: () => void;
  private readonly transport: SafetyEventTransport | null;

  public constructor(options: ProductionClientOptions & { onPanic?: () => void; safetyTransport?: SafetyEventTransport } = {}) {
    this.onPanic = options.onPanic ?? (() => undefined);
    this.transport = options.safetyTransport ?? null;
    this.transport?.subscribe((snapshot) => this.update(snapshot));
  }

  public getSnapshot(): SafetySnapshot {
    return this.snapshotValue;
  }

  public subscribe(listener: (snapshot: SafetySnapshot) => void): () => void {
    this.listeners.listeners.add(listener);
    return () => this.listeners.listeners.delete(listener);
  }

  public async refresh(): Promise<void> {
    if (!this.transport) {
      this.update({ detail: "The #13 safety event transport is not connected; protected publication is blocked.", state: "blocked" });
      return;
    }
    try {
      await this.transport.refresh();
      this.update(this.transport.getSnapshot());
    } catch {
      this.update({ detail: "The #13 safety event transport failed; protected publication is blocked.", state: "blocked" });
    }
  }

  public async triggerPanic(): Promise<void> {
    this.onPanic();
    if (!this.transport) {
      this.update({ detail: "Panic stop was applied locally; the #13 event transport is not connected.", state: "panic" });
      return;
    }
    try {
      await this.transport.triggerPanic();
      this.update(this.transport.getSnapshot());
    } catch {
      this.update({ detail: "Panic stop was applied locally; the #13 event transport did not acknowledge it.", state: "panic" });
    }
  }

  public async clear(): Promise<void> {
    if (!this.transport) {
      this.update({ detail: "The #13 safety event transport is not connected; protected publication remains blocked.", state: "blocked" });
      return;
    }
    try {
      await this.transport.clear();
      this.update(this.transport.getSnapshot());
    } catch {
      this.update({ detail: "The #13 safety recovery event was not acknowledged; protected publication remains blocked.", state: "blocked" });
    }
  }

  private update(snapshot: SafetySnapshot): void {
    this.snapshotValue = snapshot;
    this.listeners.notify(snapshot);
  }
}

export interface ProductionCreatorConsoleOptions extends ProductionClientOptions {
  mediaClient?: MediaSessionClient<MediaStream, MediaStream>;
  safetyTransport?: SafetyEventTransport;
}

export function createProductionCreatorConsoleClients(options: ProductionCreatorConsoleOptions = {}): CreatorConsoleClients {
  const media = new ProductionMediaSessionClient(options.mediaClient);
  return {
    media,
    enrollment: new ProductionEnrollmentClient(options),
    readiness: new ProductionReadinessClient(options),
    safety: new ProductionSafetyClient({ ...options, onPanic: () => media.stop() }),
  };
}
