import { describe, expect, it } from "vitest";

import { encodePcm16, PcmChunkBuffer, pcmMimeType } from "./pcmRecorder";

describe("local PCM recorder", () => {
  it("encodes clamped mono samples as signed 16-bit little-endian PCM", () => {
    const encoded = encodePcm16(new Float32Array([-2, -1, 0, 0.5, 1, 2]));
    const view = new DataView(encoded.buffer);

    expect(Array.from({ length: 6 }, (_, index) => view.getInt16(index * 2, true))).toEqual([
      -32768,
      -32768,
      0,
      16383,
      32767,
      32767,
    ]);
  });

  it("declares the exact local transport format and sample rate", () => {
    expect(pcmMimeType(48_000)).toBe(
      "audio/pcm;format=s16le;rate=48000;channels=1",
    );
  });

  it("batches callbacks and flushes pending PCM exactly once", () => {
    const chunks = new PcmChunkBuffer(4);
    expect(chunks.push(new Uint8Array([1, 2]))).toBeNull();
    expect(chunks.push(new Uint8Array([3, 4]))).toEqual(
      new Uint8Array([1, 2, 3, 4]),
    );
    expect(chunks.flush()).toBeNull();
    expect(chunks.push(new Uint8Array([5]))).toBeNull();
    expect(chunks.flush()).toEqual(new Uint8Array([5]));
  });
});
