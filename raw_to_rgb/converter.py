import sys
import subprocess
from pathlib import Path

RAW_EXTENSIONS = {".arw", ".cr2", ".cr3", ".nef", ".orf", ".rw2", ".dng", ".raf", ".raw"}

# Fixed flags for native-RGB output:
#   -r 1 1 1 1  no white-balance scaling (unity multipliers)
#   -M          use embedded colour matrix
#   -o 0        no output colour-space conversion (camera-native)
#   -W          no auto-brightness
#   -4          linear 16-bit output
#   -T          write TIFF
BASE_OPTIONS: list[str] = ["-r", "1", "1", "1", "1", "-M", "-o", "0", "-W", "-4", "-T"]

# (label, debayer flags) pairs for the debayer algorithm selector
DEBAYER_ALGORITHMS: list[tuple[str, list[str]]] = [
    ("DHT (12) — recommended",              ["-q", "12"]),
    ("AHD (3)",                             ["-q", "3"]),
    ("Modified AHD / AAHD (13)",            ["-q", "13"]),
    ("LMMSE (11)",                          ["-q", "11"]),
    ("DCB (4)",                             ["-q", "4"]),
    ("PPG (2)",                             ["-q", "2"]),
    ("VNG (1)",                             ["-q", "1"]),
    ("Bilinear (0)",                        ["-q", "0"]),
    ("No Debayer — Half Resolution Output", ["-q", "0", "-h"]),
]

_BIN_ROOT = Path(__file__).parent.parent / "bin"


def binary_path() -> Path:
    if sys.platform == "win32":
        return _BIN_ROOT / "windows" / "dcraw_emu.exe"
    else:
        return _BIN_ROOT / "macos" / "dcraw_emu"


class Converter:
    def __init__(self):
        self.binary = binary_path()

    def check_binary(self) -> bool:
        return self.binary.exists() and self.binary.is_file()

    def convert_batch(
        self,
        input_dir: Path,
        output_dir: Path,
        options: list[str],
        log_fn=print,
    ) -> None:
        if not self.check_binary():
            log_fn(f"[ERROR] dcraw_emu not found at: {self.binary}")
            return

        raw_files = sorted(
            f for f in input_dir.iterdir() if f.suffix.lower() in RAW_EXTENSIONS
        )
        if not raw_files:
            log_fn("No RAW files found in the input folder.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        log_fn(f"Found {len(raw_files)} RAW file(s). Starting conversion...")

        for raw_file in raw_files:
            self._convert_one(raw_file, output_dir, options, log_fn)

        log_fn("All done.")

    def _convert_one(
        self,
        raw_file: Path,
        output_dir: Path,
        options: list[str],
        log_fn=print,
    ) -> None:
        cmd = [str(self.binary)] + options + [str(raw_file)]
        log_fn(f"  {raw_file.name} ...")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(output_dir),
            )
            if result.returncode != 0:
                log_fn(f"    [ERROR] {result.stderr.strip() or result.stdout.strip()}")
            else:
                log_fn(f"    OK")
        except Exception as exc:
            log_fn(f"    [EXCEPTION] {exc}")
