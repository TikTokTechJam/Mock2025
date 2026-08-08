import type {
  MediaSessionClient,
  MediaSessionOutput,
  MediaSessionStartRequest,
} from "./media-session-client";

export type CapabilityId = "face" | "license_plate" | "visual_pii" | "spoken_pii";
export type CapabilityState = "ready" | "processing" | "unavailable";
export type EnrollmentState = "not_enrolled" | "capturing" | "ready" | "error";
export type SafetyState = "normal" | "degraded" | "blocked" | "panic";

export interface CapabilityReadiness {
  id: CapabilityId;
  label: string;
  detail: string;
  enabled: boolean;
  required: boolean;
  state: CapabilityState;
}

export interface EnrollmentSnapshot {
  detail: string;
  state: EnrollmentState;
}

export interface SafetySnapshot {
  detail: string;
  state: SafetyState;
}

export interface UnprotectedSourceHandle {
  readonly kind: "unprotected-source";
  readonly label: string;
}

export interface ProtectedStreamHandle {
  readonly kind: "protected-output";
  readonly label: string;
  readonly redactions: readonly string[];
}

export type MockMediaSessionOutput = MediaSessionOutput<UnprotectedSourceHandle, ProtectedStreamHandle>;
export type MockMediaSessionClient = MediaSessionClient<UnprotectedSourceHandle, ProtectedStreamHandle>;

type Listener<T> = (snapshot: T) => void;

export interface CreatorConsoleClients {
  enrollment: MockEnrollmentClient;
  media: MockMediaSessionClient;
  readiness: MockReadinessClient;
  safety: MockSafetyClient;
}

const initialCapabilities: CapabilityReadiness[] = [
  {
    id: "face",
    label: "Bystander faces",
    detail: "Protect all detected faces unless an approved creator identity is ready.",
    enabled: true,
    required: true,
    state: "ready",
  },
  {
    id: "license_plate",
    label: "License plates",
    detail: "Cover detected vehicle plates in the protected output.",
    enabled: true,
    required: true,
    state: "ready",
  },
  {
    id: "visual_pii",
    label: "Visual text PII",
    detail: "Protect supported sensitive text regions when the visual adapter is available.",
    enabled: true,
    required: false,
    state: "ready",
  },
  {
    id: "spoken_pii",
    label: "Spoken PII",
    detail: "Mute supported sensitive speech intervals in the protected audio path.",
    enabled: true,
    required: true,
    state: "ready",
  },
];

export class MockReadinessClient {
  private snapshotValue = initialCapabilities;
  private readonly listeners = new Set<Listener<CapabilityReadiness[]>>();

  public getSnapshot(): CapabilityReadiness[] {
    return this.snapshotValue;
  }

  public subscribe(listener: Listener<CapabilityReadiness[]>): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public setEnabled(id: CapabilityId, enabled: boolean): void {
    this.snapshotValue = this.snapshotValue.map((capability) =>
      capability.id === id ? { ...capability, enabled } : capability,
    );
    this.notify();
  }

  public setState(id: CapabilityId, state: CapabilityState, detail: string): void {
    this.snapshotValue = this.snapshotValue.map((capability) =>
      capability.id === id ? { ...capability, state, detail } : capability,
    );
    this.notify();
  }

  public reset(): void {
    this.snapshotValue = initialCapabilities.map((capability) => ({ ...capability }));
    this.notify();
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener(this.snapshotValue));
  }
}

export class MockEnrollmentClient {
  private snapshotValue: EnrollmentSnapshot = {
    detail: "No creator identity is enrolled. All detected faces remain protected.",
    state: "not_enrolled",
  };
  private readonly listeners = new Set<Listener<EnrollmentSnapshot>>();

  public getSnapshot(): EnrollmentSnapshot {
    return this.snapshotValue;
  }

  public subscribe(listener: Listener<EnrollmentSnapshot>): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public capture(): void {
    this.snapshotValue = this.snapshotValue.state === "capturing"
      ? {
          detail: "Mock creator enrollment is ready; ambiguous matches remain protected.",
          state: "ready",
        }
      : {
          detail: "Mock capture is in progress. Confirm the sample to finish enrollment.",
          state: "capturing",
        };
    this.notify();
  }

  public remove(): void {
    this.snapshotValue = {
      detail: "Enrollment removed. All detected faces remain protected.",
      state: "not_enrolled",
    };
    this.notify();
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener(this.snapshotValue));
  }
}

export class MockSafetyClient {
  private snapshotValue: SafetySnapshot = {
    detail: "Required mock protections are ready for the protected preview.",
    state: "normal",
  };
  private readonly listeners = new Set<Listener<SafetySnapshot>>();

  public getSnapshot(): SafetySnapshot {
    return this.snapshotValue;
  }

  public subscribe(listener: Listener<SafetySnapshot>): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public triggerPanic(): void {
    this.snapshotValue = {
      detail: "Panic is active. Protected publication is blocked.",
      state: "panic",
    };
    this.notify();
  }

  public clear(): void {
    this.snapshotValue = {
      detail: "Required mock protections are ready for the protected preview.",
      state: "normal",
    };
    this.notify();
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener(this.snapshotValue));
  }
}

export class MockMediaSessionClientImpl implements MockMediaSessionClient {
  private active = false;

  public async start(_request: MediaSessionStartRequest): Promise<MockMediaSessionOutput> {
    this.active = true;
    return {
      sourceStream: {
        kind: "unprotected-source",
        label: "Mock camera + microphone source",
      },
      protectedStream: {
        kind: "protected-output",
        label: "Mock protected stream",
        redactions: ["bystander faces", "license plates", "supported spoken PII"],
      },
    };
  }

  public stop(): void {
    this.active = false;
  }

  public isActive(): boolean {
    return this.active;
  }
}

export function createMockCreatorConsoleClients(): CreatorConsoleClients {
  return {
    enrollment: new MockEnrollmentClient(),
    media: new MockMediaSessionClientImpl(),
    readiness: new MockReadinessClient(),
    safety: new MockSafetyClient(),
  };
}
