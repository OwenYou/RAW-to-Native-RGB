# RAW to Native RGB

Batch GUI for converting camera RAW files to **native RGB TIFF** using [LibRaw](https://www.libraw.org/) (`dcraw_emu`).

Output files are **linear, 16-bit, camera-native colour space** — no white balance scaling, no tone curve, no colour space conversion. Designed as a lossless first step before further processing in software that can accept native RGB data.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (dependency/environment manager)
- `dcraw_emu` binary from LibRaw (see below)

## Getting dcraw_emu

**Windows** — download a pre-built binary from the [LibRaw download page](https://www.libraw.org/download) and place `dcraw_emu.exe` at:
```
bin/windows/dcraw_emu.exe
```

**macOS** — install via Homebrew, then copy:
```bash
brew install libraw
cp $(which dcraw_emu) bin/macos/dcraw_emu
```

You can also use the downloaded binary on macOS.

## Running

```bash
uv run python -m raw_to_rgb
```

On first launch the log area confirms whether the binary was found.

## Supported RAW formats

`.arw` `.cr2` `.cr3` `.nef` `.orf` `.rw2` `.dng` `.raf` `.raw`

## GUI overview

| Section | Description |
|---|---|
| **Input RAW files** | Add individual files; supports multi-select and removal |
| **Output folder** | Leave blank to write TIFFs beside each source file |
| **Debayer algorithm** | Select demosaicing algorithm (see below) |
| **Parallel jobs** | Number of files to convert simultaneously (1–8) |
| **Progress** | Indeterminate activity bar + overall file counter |
| **Log** | Per-file output from `dcraw_emu`; cleared on each run |

The Convert button toggles to **Cancel**, which signals all in-flight workers to skip remaining files.

## dcraw_emu flags used

| Flag | Meaning |
|---|---|
| `-r 1 1 1 1` | Unity white-balance multipliers (no scaling) |
| `-M` | Apply embedded colour matrix |
| `-o 0` | No output colour space conversion (camera native) |
| `-W` | No auto-brightness |
| `-q <N>` | Debayer algorithm (user-selected) |
| `-4` | Linear 16-bit output |
| `-T` | Write TIFF |

## Debayer algorithms

| Value | Name | Notes |
|---|---|---|
| 12 | DHT | Default — high quality, slower |
| 3 | AHD | Adaptive Homogeneity-Directed |
| 13 | Modified AHD (AAHD) | |
| 11 | LMMSE | Good for high ISO / noisy files |
| 4 | DCB | |
| 2 | PPG | |
| 1 | VNG | Variable Number of Gradients |
| 0 | Bilinear | Fastest, lowest quality |
