# forensic/

Experimental signature-match, sensor-noise injection, and covert-channel modules
for the Mendacity offensive-deception toolchain.

This folder is **deliberately separate** from `src/mendacity/` while it stabilises.
Once each module passes its self-test under operational conditions it can be wired
into the mission pipeline as a new stage.

## Scope

Four layered capabilities, each addressing a different forensic axis:

| Module | Purpose | Defeats |
|---|---|---|
| `signature/` | Match donor-device byte-level signatures (thumbnail, JPEG quant tables, ICC, MakerNote) | 5-minute ExifTool audit |
| `prnu/` | Extract sensor-noise fingerprint from a reference corpus and inject it into synthetic imagery | PRNU correlation tests |
| `steg/` | Key-permuted spatial-LSB covert channel for asset comms (URL / instructions / next-contact) | Steganalysis at low payload |
| `laundering/` | Re-photograph simulation + spectrum rebalancing + surrogate AI-detector grading | Pixel-level CNN classifiers (Hive AI / Optic / SDXL-detector class) |

Out of scope: anything that executes code on a viewer's device. See PALANTIR_BRIEF.md
for authority boundaries (Title 10 §1631 IO; CNO is a different authority).

## Demo result (2026-05-03 smoke)

On `assets/image-9fab1a24-...` (DALL-E synthetic war image), against
**Organika/sdxl-detector** (HuggingFace ViT, public surrogate):

| Stage | p(AI) | label |
|---|---|---|
| Raw DALL-E output | **97.7%** | artificial |
| After `launder` (default params) | 52.9% | artificial |
| After `launder` (aggressive params) | 11.2% | **human** (flipped) |
| After `launder-sweep` best (psf=1.3, chroma=2.4, noise=3.2, blend=0.8) | **0.04%** | **human** |

Visual fidelity at the most aggressive setting: **PSNR 24.8 dB, RMSE 14.6** — slight
softening, content fully intact. Side-by-side comparison renderable via
`launder-compare` to a single PNG with detector scores burned in.

Honest cross-detector caveats:

- The *same* aggressive output, scored against **umm-maybe/AI-image-detector** (older
  general model), went 43.1% → 54.8% AI: *up*, not down. Different detectors key on
  different signals; what flattens one can excite another.
- Commercial detectors (Hive AI, Optic, Reality Defender) are not tested here. Public
  surrogates indicate pixel-level signal has been altered; transfer to closed
  commercial detectors is *probable but not certain*.
- The bottom line: for the demo, run `launder-sweep` on your specific image against
  whatever detector(s) the judges run, lock in the best params, and ship.

## Layout

```
forensic/
├── README.md                 # this file
├── requirements.txt          # extra deps (PyWavelets, etc.)
├── cli.py                    # `mendacity-forensic` entrypoint
├── signature/
│   ├── thumbnail.py          # regenerate embedded EXIF thumbnail
│   ├── quantization.py       # match JPEG quantization tables
│   ├── icc_profile.py        # Display P3 / sRGB ICC tagging
│   └── makernote.py          # preserve Apple MakerNote block
├── prnu/
│   ├── extract.py            # wavelet PRNU extraction from a reference corpus
│   └── inject.py             # additive PRNU injection
├── steg/
│   ├── embed.py              # adaptive DCT-LSB embedding (survives JPEG recompression)
│   ├── extract.py            # decode embedded payload
│   └── analyze.py            # chi-squared + RS analysis self-check
├── tests/                    # pytest unit tests for each module
└── fixtures/                 # reference images for tests / PRNU corpus
```

## Install

```bash
cd forensic
pip install -r requirements.txt
```

Then add the repo root to `PYTHONPATH` or run the CLI directly:

```bash
python -m forensic.cli signature-match --donor ref.jpg --target ai.jpg --output out.jpg
python -m forensic.cli prnu-extract  --corpus fixtures/iphone_x/ --output prnu.npy
python -m forensic.cli prnu-inject   --target ai.jpg --prnu prnu.npy --output out.jpg
python -m forensic.cli steg-embed    --image cover.jpg --payload '{"url":"..."}' --key SECRET --output steg.jpg
python -m forensic.cli steg-extract  --image steg.jpg --key SECRET
python -m forensic.cli steg-analyze  --cover cover.jpg --stego steg.jpg
python -m forensic.cli full-stack    --target ai.jpg --donor ref.jpg --prnu prnu.npy \\
                                     --payload '{"url":"..."}' --key SECRET --output final.jpg
```

## Honesty caveats

Nothing here is "permanently undetectable." Every technique below has a detection
half-life measured in months-to-years:

- **Signature match** loses to a forensic analyst with ExifTool and 5 minutes who
  has reference photos from the *specific physical device* claimed.
- **PRNU injection** loses if the analyst has reference imagery from the *exact
  serial-numbered* device claimed (sensor noise is per-unit, not per-model).
  Without that reference, "PRNU consistent with device class" passes.
- **Steg** at low payload (<5%) using DCT-domain embedding survives free public
  steganalysis tools and Telegram's photo-upload recompression. State-actor bulk
  steganalysis with current-gen CNN detectors will probabilistically flag it on
  large enough samples.

The durable claim isn't "we beat detectors." It's: **we run the same detector
stack the adversary runs, and we self-grade**. Each tier ships with a self-check
that scores the synthetic output and aborts if it scores too high.

## Status

| Module | Status |
|---|---|
| signature/thumbnail.py | functional |
| signature/quantization.py | functional |
| signature/icc_profile.py | functional |
| signature/makernote.py | functional |
| prnu/extract.py | functional |
| prnu/inject.py | functional |
| steg/embed.py | functional |
| steg/extract.py | functional |
| steg/analyze.py | functional |
| cli.py | functional |
