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
  private readonly processor: ScriptProcessorNode;
  private readonly silentOutput: GainNode;

  constructor(stream: MediaStream) {
    super();
    this.context = new AudioContext();
    this.source = this.context.createMediaStreamSource(stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.silentOutput = this.context.createGain();
    this.silentOutput.gain.value = 0;
    this.processor.onaudioprocess = (event) => {
      if (this.state !== "recording") return;
      const pcm = encodePcm16(event.inputBuffer.getChannelData(0));
      const buffer = new ArrayBuffer(pcm.byteLength);
      new Uint8Array(buffer).set(pcm);
      const data = new Blob([buffer], { type: pcmMimeType(this.context.sampleRate) });
      this.dispatchEvent(new BlobEvent("dataavailable", { data }));
    };
  }

  start(): void {
    if (this.state !== "inactive") throw new DOMException("Recorder is already active");
    this.state = "recording";
    this.source.connect(this.processor);
    this.processor.connect(this.silentOutput);
    this.silentOutput.connect(this.context.destination);
    void this.context.resume();
  }

  requestData(): void {
    // PCM chunks are emitted continuously from the audio processing callback.
  }

  stop(): void {
    if (this.state !== "recording") return;
    this.state = "inactive";
    this.processor.onaudioprocess = null;
    this.source.disconnect();
    this.processor.disconnect();
    this.silentOutput.disconnect();
    void this.context.close();
    this.dispatchEvent(new Event("stop"));
  }
}
