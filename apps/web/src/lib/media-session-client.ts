export interface MediaSessionStartRequest {
  cameraId: string;
  microphoneId: string;
  privacyPolicyId: string;
}

export interface MediaSessionOutput<TSourceStream, TProtectedStream> {
  sourceStream: TSourceStream;
  protectedStream: TProtectedStream;
}

export interface MediaSessionClient<TSourceStream, TProtectedStream> {
  start(request: MediaSessionStartRequest): Promise<MediaSessionOutput<TSourceStream, TProtectedStream>>;
  stop(): void;
}
