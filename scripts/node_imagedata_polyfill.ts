/**
 * Minimal `ImageData` for Node so SynthIDBye can run `new ImageData(buf, w, h)`.
 * Import this module once before loading `imageProcessor.ts`.
 */
class ImageDataPolyfill {
  readonly data: Uint8ClampedArray;
  readonly width: number;
  readonly height: number;

  constructor(sw: number, sh: number);
  constructor(data: Uint8ClampedArray, sw: number, sh: number);
  constructor(
    arg1: number | Uint8ClampedArray,
    arg2?: number,
    arg3?: number,
  ) {
    if (arg1 instanceof Uint8ClampedArray) {
      this.data = arg1;
      this.width = arg2!;
      this.height = arg3!;
    } else {
      this.width = arg1;
      this.height = arg2!;
      this.data = new Uint8ClampedArray(this.width * this.height * 4);
    }
  }
}

type WithImageData = typeof globalThis & {
  ImageData?: typeof ImageDataPolyfill;
};

const g = globalThis as WithImageData;
if (typeof g.ImageData === "undefined") {
  g.ImageData = ImageDataPolyfill as unknown as typeof ImageData;
}
