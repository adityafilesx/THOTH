export function encodePcm16(samples: Float32Array): Uint8Array {
  const encoded = new Uint8Array(samples.length * 2);
  const view = new DataView(encoded.buffer);
  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    const value = clamped < 0 ? Math.round(clamped * 32768) : Math.floor(clamped * 32767);
    view.setInt16(index * 2, value, true);
  });
  return encoded;
}

export function pcmMimeType(sampleRate: number): string {
  return `audio/pcm;format=s16le;rate=${sampleRate};channels=1`;
}

export class PcmChunkBuffer {
  private chunks: Uint8Array[] = [];
  private byteLength = 0;

  constructor(private readonly targetBytes: number) {}

  push(chunk: Uint8Array): Uint8Array | null {
    if (chunk.byteLength === 0) return null;
    this.chunks.push(chunk);
    this.byteLength += chunk.byteLength;
    return this.byteLength >= this.targetBytes ? this.flush() : null;
  }

  flush(): Uint8Array | null {
    if (this.byteLength === 0) return null;
    const combined = new Uint8Array(this.byteLength);
    let offset = 0;
    for (const chunk of this.chunks) {
      combined.set(chunk, offset);
      offset += chunk.byteLength;
    }
    this.chunks = [];
    this.byteLength = 0;
    return combined;
  }
}

/**
 * Local mono PCM capture for the bundled whisper.cpp runtime.
 *
 * MediaRecorder emits WebM/Opus in Chromium and WebKit, while the pinned
 * whisper-cli accepts WAV/PCM-family input. This recorder emits bounded raw
 * PCM chunks that the daemon wraps in a private temporary WAV file.
 */
export class LocalPcmRecorder extends EventTarget {
  state: RecordingState = "inactive";

  private readonly context: AudioContext;
  private readonly source: MediaStreamAudioSourceNode;
  private readonly analyser: AnalyserNode;
  private readonly processor: ScriptProcessorNode;
  private readonly silentOutput: GainNode;
  private readonly chunks: PcmChunkBuffer;

  private silenceTimer: number | null = null;
  private hasSpoken = false;
  private readonly silenceThreshold = 0.01;
  private readonly silenceDurationMs = 1500;

  constructor(stream: MediaStream) {
    super();
    this.context = new AudioContext();
    this.source = this.context.createMediaStreamSource(stream);
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 512;
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.silentOutput = this.context.createGain();
    // About 500 ms of mono s16le PCM per upload.
    this.chunks = new PcmChunkBuffer(this.context.sampleRate);
    this.silentOutput.gain.value = 0;
    this.processor.onaudioprocess = (event) => {
      if (this.state !== "recording") return;
      const pcm = encodePcm16(event.inputBuffer.getChannelData(0));
      const batch = this.chunks.push(pcm);
      if (batch) this.emit(batch);

      // Voice Activity Detection
      const dataArray = new Float32Array(this.analyser.fftSize);
      this.analyser.getFloatTimeDomainData(dataArray);
      let rms = 0;
      for (let i = 0; i < dataArray.length; i++) {
        rms += dataArray[i] * dataArray[i];
      }
      rms = Math.sqrt(rms / dataArray.length);

      if (rms > this.silenceThreshold) {
        this.hasSpoken = true;
        if (this.silenceTimer !== null) {
          window.clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }
      } else if (this.hasSpoken && this.silenceTimer === null) {
        this.silenceTimer = window.setTimeout(() => {
          this.dispatchEvent(new Event("silence"));
        }, this.silenceDurationMs);
      }
    };
  }

  start(): void {
    if (this.state !== "inactive") throw new DOMException("Recorder is already active");
    this.state = "recording";
    this.hasSpoken = false;
    if (this.silenceTimer !== null) {
      window.clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this.source.connect(this.analyser);
    this.analyser.connect(this.processor);
    this.processor.connect(this.silentOutput);
    this.silentOutput.connect(this.context.destination);
    void this.context.resume();
  }

  requestData(): void {
    const pending = this.chunks.flush();
    if (pending) this.emit(pending);
  }

  stop(): void {
    if (this.state !== "recording") return;
    this.state = "inactive";
    if (this.silenceTimer !== null) {
      window.clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this.processor.onaudioprocess = null;
    try { this.source.disconnect(); } catch(e) {}
    try { this.analyser.disconnect(); } catch(e) {}
    try { this.processor.disconnect(); } catch(e) {}
    try { this.silentOutput.disconnect(); } catch(e) {}
    try { void this.context.close(); } catch(e) { console.error("Close failed", e); }
    this.dispatchEvent(new Event("stop"));
  }

  private emit(pcm: Uint8Array): void {
    const buffer = new ArrayBuffer(pcm.byteLength);
    new Uint8Array(buffer).set(pcm);
    const data = new Blob([buffer], { type: pcmMimeType(this.context.sampleRate) });
    this.dispatchEvent(new BlobEvent("dataavailable", { data }));
  }
}
