import { describe, expect, it } from "vitest";

import { encodePcm16, pcmMimeType } from "./pcmRecorder";

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
});
