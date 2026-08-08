import type {
  MediaSessionClient,
  MediaSessionOutput,
  MediaSessionStartRequest,
} from "./media-session-client";

export type BrowserMediaSessionState = "idle" | "starting" | "live" | "stopping" | "error";

export interface MediaFrameSnapshot {
  sourceTimestampMs: number;
  pendingVideoFrames: number;
}

export interface BrowserMediaSessionCallbacks {
  onFrame?: (snapshot: MediaFrameSnapshot) => void;
  onError?: (message: string) => void;
}

export type BrowserMediaSessionStartResult = MediaSessionOutput<MediaStream, MediaStream>;

const VIDEO_FRAME_RATE = 30;
const MAX_PENDING_VIDEO_FRAMES = 1;
const AUDIO_CYCLE_MS = 2_000;
const AUDIO_MUTE_START_MS = 1_500;
const AUDIO_MUTE_DURATION_MS = 500;
const REMOTE_TRACK_TIMEOUT_MS = 10_000;

function errorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Camera or microphone permission was denied. Allow both devices and try again.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "The browser media session failed unexpectedly.";
}

function waitForVideoMetadata(video: HTMLVideoElement): Promise<void> {
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    let timeout = 0;

    function cleanup(): void {
      window.clearTimeout(timeout);
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
      video.removeEventListener("error", onError);
    }
    function onLoadedMetadata(): void {
      cleanup();
      resolve();
    }
    function onError(): void {
      cleanup();
      reject(new Error("The captured video could not be decoded."));
    }

    timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("The captured video did not provide media metadata."));
    }, REMOTE_TRACK_TIMEOUT_MS);
    video.addEventListener("loadedmetadata", onLoadedMetadata, { once: true });
    video.addEventListener("error", onError, { once: true });
  });
}

export class BrowserMediaSession implements MediaSessionClient<MediaStream, MediaStream> {
  private readonly callbacks: BrowserMediaSessionCallbacks;
  private captureStream: MediaStream | null = null;
  private processedStream: MediaStream | null = null;
  private remoteStream: MediaStream | null = null;
  private senderConnection: RTCPeerConnection | null = null;
  private receiverConnection: RTCPeerConnection | null = null;
  private sourceVideo: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private canvasContext: CanvasRenderingContext2D | null = null;
  private audioContext: AudioContext | null = null;
  private audioGain: GainNode | null = null;
  private videoFrameRequest: number | null = null;
  private videoFrameUsesMediaCallback = false;
  private audioSchedule: number | null = null;
  private sourceEpochMs = 0;
  private stopped = false;
  private failureReported = false;

  public constructor(callbacks: BrowserMediaSessionCallbacks = {}) {
    this.callbacks = callbacks;
  }

  public async start(_request: MediaSessionStartRequest = { cameraId: "default", microphoneId: "default", privacyPolicyId: "default" }): Promise<BrowserMediaSessionStartResult> {
    if (this.captureStream) {
      throw new Error("The browser media session has already started.");
    }

    this.stopped = false;
    this.failureReported = false;

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser does not provide camera and microphone capture.");
      }

      this.captureStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: true,
      });
      this.sourceEpochMs = performance.now();
      this.captureStream.getTracks().forEach((track) => {
        track.addEventListener("ended", () => {
          this.fail("The camera or microphone disconnected.");
        });
      });

      const remoteStream = await this.connectLoopback(this.captureStream);
      this.remoteStream = remoteStream;
      await this.createProcessedOutput(remoteStream);

      return {
        sourceStream: this.captureStream,
        protectedStream: this.processedStream as MediaStream,
      };
    } catch (error) {
      this.stop();
      this.reportFailure(errorMessage(error));
      throw error;
    }
  }

  public stop(): void {
    if (this.stopped) {
      return;
    }

    this.stopped = true;
    if (this.videoFrameRequest !== null) {
      if (this.videoFrameUsesMediaCallback && this.sourceVideo?.cancelVideoFrameCallback) {
        this.sourceVideo.cancelVideoFrameCallback(this.videoFrameRequest);
      } else {
        window.cancelAnimationFrame(this.videoFrameRequest);
      }
      this.videoFrameRequest = null;
    }
    if (this.audioSchedule !== null) {
      window.clearTimeout(this.audioSchedule);
      this.audioSchedule = null;
    }

    this.captureStream?.getTracks().forEach((track) => track.stop());
    this.processedStream?.getTracks().forEach((track) => track.stop());
    this.remoteStream?.getTracks().forEach((track) => track.stop());
    this.senderConnection?.close();
    this.receiverConnection?.close();
    this.sourceVideo?.pause();
    if (this.sourceVideo) {
      this.sourceVideo.srcObject = null;
    }
    this.sourceVideo = null;
    this.canvas = null;
    this.canvasContext = null;
    this.captureStream = null;
    this.processedStream = null;
    this.remoteStream = null;
    this.senderConnection = null;
    this.receiverConnection = null;
    this.audioGain = null;
    const audioContext = this.audioContext;
    this.audioContext = null;
    if (audioContext) {
      void audioContext.close();
    }
  }

  private async connectLoopback(captureStream: MediaStream): Promise<MediaStream> {
    const sender = new RTCPeerConnection();
    const receiver = new RTCPeerConnection();
    const remoteStream = new MediaStream();
    this.senderConnection = sender;
    this.receiverConnection = receiver;

    let receiverRemoteDescriptionReady = false;
    let senderRemoteDescriptionReady = false;
    const senderCandidates: RTCIceCandidate[] = [];
    const receiverCandidates: RTCIceCandidate[] = [];

    const addCandidates = async (
      connection: RTCPeerConnection,
      candidates: RTCIceCandidate[],
    ) => {
      await Promise.all(candidates.splice(0).map((candidate) => connection.addIceCandidate(candidate)));
    };

    sender.onicecandidate = (event) => {
      if (!event.candidate) {
        return;
      }
      if (receiverRemoteDescriptionReady) {
        void receiver.addIceCandidate(event.candidate).catch((error) => this.fail(errorMessage(error)));
      } else {
        senderCandidates.push(event.candidate);
      }
    };
    receiver.onicecandidate = (event) => {
      if (!event.candidate) {
        return;
      }
      if (senderRemoteDescriptionReady) {
        void sender.addIceCandidate(event.candidate).catch((error) => this.fail(errorMessage(error)));
      } else {
        receiverCandidates.push(event.candidate);
      }
    };

    const remoteTracks = new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        reject(new Error("The media transport did not return both processed input tracks."));
      }, REMOTE_TRACK_TIMEOUT_MS);
      const seenKinds = new Set<string>();
      const onTrack = (event: RTCTrackEvent) => {
        if (!remoteStream.getTracks().some((track) => track.id === event.track.id)) {
          remoteStream.addTrack(event.track);
        }
        seenKinds.add(event.track.kind);
        event.track.addEventListener("ended", () => this.fail("The media transport disconnected."));
        if (seenKinds.has("audio") && seenKinds.has("video")) {
          window.clearTimeout(timeout);
          resolve();
        }
      };
      receiver.ontrack = onTrack;
    });

    const onConnectionStateChange = (event: Event) => {
      const connection = event.currentTarget as RTCPeerConnection;
      if (connection.connectionState === "failed" || connection.connectionState === "closed") {
        this.fail("The media transport disconnected.");
      }
    };
    sender.addEventListener("connectionstatechange", onConnectionStateChange);
    receiver.addEventListener("connectionstatechange", onConnectionStateChange);

    captureStream.getTracks().forEach((track) => sender.addTrack(track, captureStream));
    const offer = await sender.createOffer();
    await sender.setLocalDescription(offer);
    await receiver.setRemoteDescription(sender.localDescription ?? offer);
    receiverRemoteDescriptionReady = true;
    await addCandidates(receiver, senderCandidates);

    const answer = await receiver.createAnswer();
    await receiver.setLocalDescription(answer);
    await sender.setRemoteDescription(receiver.localDescription ?? answer);
    senderRemoteDescriptionReady = true;
    await addCandidates(sender, receiverCandidates);

    await remoteTracks;
    return remoteStream;
  }

  private async createProcessedOutput(remoteStream: MediaStream): Promise<void> {
    const sourceVideo = document.createElement("video");
    sourceVideo.muted = true;
    sourceVideo.playsInline = true;
    sourceVideo.srcObject = remoteStream;
    this.sourceVideo = sourceVideo;
    await waitForVideoMetadata(sourceVideo);
    await sourceVideo.play();

    const canvas = document.createElement("canvas");
    const canvasContext = canvas.getContext("2d");
    if (!canvasContext) {
      throw new Error("The browser could not create the mock video processor.");
    }
    this.canvas = canvas;
    this.canvasContext = canvasContext;

    const canvasStream = canvas.captureStream(VIDEO_FRAME_RATE);
    const processedVideoTrack = canvasStream.getVideoTracks()[0];
    if (!processedVideoTrack) {
      throw new Error("The browser could not create a processed video track.");
    }

    if (typeof AudioContext === "undefined") {
      throw new Error("This browser does not provide the audio processing boundary.");
    }
    const audioContext = new AudioContext();
    this.audioContext = audioContext;
    await audioContext.resume();
    const audioSource = audioContext.createMediaStreamSource(remoteStream);
    const audioGain = audioContext.createGain();
    const audioDestination = audioContext.createMediaStreamDestination();
    audioSource.connect(audioGain).connect(audioDestination);
    this.audioGain = audioGain;
    const processedAudioTrack = audioDestination.stream.getAudioTracks()[0];
    if (!processedAudioTrack) {
      throw new Error("The browser could not create a processed audio track.");
    }

    this.processedStream = new MediaStream([processedVideoTrack, processedAudioTrack]);
    this.scheduleAudioMute();
    this.drawProcessedFrame();
  }

  private drawProcessedFrame = (sourceMediaTimestampMs?: number): void => {
    if (this.stopped || !this.sourceVideo || !this.canvas || !this.canvasContext) {
      return;
    }

    try {
      const width = this.sourceVideo.videoWidth || 640;
      const height = this.sourceVideo.videoHeight || 360;
      this.canvas.width = width;
      this.canvas.height = height;
      this.canvasContext.drawImage(this.sourceVideo, 0, 0, width, height);

      const boxWidth = Math.round(width * 0.34);
      const boxHeight = Math.round(height * 0.24);
      const boxX = Math.round((width - boxWidth) / 2);
      const boxY = Math.round((height - boxHeight) / 2);
      this.canvasContext.fillStyle = "#dc2626";
      this.canvasContext.fillRect(boxX, boxY, boxWidth, boxHeight);
      this.canvasContext.fillStyle = "#ffffff";
      this.canvasContext.font = `${Math.max(12, Math.round(width / 42))}px sans-serif`;
      this.canvasContext.textAlign = "center";
      this.canvasContext.textBaseline = "middle";
      this.canvasContext.fillText("MOCK REDACTION", width / 2, height / 2);

      const sourceTimestampMs = Math.max(0, Math.round(sourceMediaTimestampMs ?? performance.now() - this.sourceEpochMs));
      this.callbacks.onFrame?.({
        sourceTimestampMs,
        pendingVideoFrames: 0,
      });
      this.scheduleNextVideoFrame();
    } catch (error) {
      this.fail(errorMessage(error));
    }
  };

  private scheduleNextVideoFrame(): void {
    if (this.stopped || !this.sourceVideo) {
      return;
    }

    if (this.sourceVideo.requestVideoFrameCallback) {
      this.videoFrameUsesMediaCallback = true;
      this.videoFrameRequest = this.sourceVideo.requestVideoFrameCallback((_now, metadata) => {
        this.drawProcessedFrame(metadata.mediaTime * 1_000);
      });
      return;
    }

    this.videoFrameUsesMediaCallback = false;
    this.videoFrameRequest = window.requestAnimationFrame(() => this.drawProcessedFrame());
  }

  private scheduleAudioMute = (): void => {
    if (this.stopped || !this.audioContext || !this.audioGain) {
      return;
    }

    const startAt = this.audioContext.currentTime + 0.1;
    const muteStartAt = startAt + AUDIO_MUTE_START_MS / 1_000;
    const muteEndAt = muteStartAt + AUDIO_MUTE_DURATION_MS / 1_000;
    this.audioGain.gain.cancelScheduledValues(startAt);
    this.audioGain.gain.setValueAtTime(1, startAt);
    this.audioGain.gain.setValueAtTime(0, muteStartAt);
    this.audioGain.gain.setValueAtTime(0, muteEndAt);
    this.audioGain.gain.setValueAtTime(1, muteEndAt + 0.01);
    this.audioSchedule = window.setTimeout(this.scheduleAudioMute, AUDIO_CYCLE_MS);
  };

  private fail(message: string): void {
    if (this.stopped || this.failureReported) {
      return;
    }

    this.reportFailure(message);
    this.stop();
  }

  private reportFailure(message: string): void {
    if (this.failureReported) {
      return;
    }
    this.failureReported = true;
    this.callbacks.onError?.(message);
  }
}

export { MAX_PENDING_VIDEO_FRAMES };
