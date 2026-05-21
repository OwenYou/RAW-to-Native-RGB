# CLAUDE.md

## Project

Batch GUI that converts camera RAW files to native RGB TIFF via the `dcraw_emu` binary from LibRaw. The goal is a **lossless, camera-native** output: linear 16-bit, no WB scaling, no colour space conversion.

## Running

```bash
uv run python -m raw_to_rgb
```

## Project layout

```
bin/
  windows/dcraw_emu.exe   # user-supplied; gitignored
  macos/dcraw_emu         # user-supplied; gitignored
raw_to_rgb/
  __main__.py             # entry point — instantiates App and calls mainloop()
  gui.py                  # tkinter GUI (App extends tk.Tk)
  converter.py            # binary path resolution, BASE_OPTIONS, DEBAYER_ALGORITHMS
pyproject.toml            # uv/hatchling config, requires-python = ">=3.12"
```

## Architecture

### converter.py
- `binary_path()` — resolves `bin/windows/dcraw_emu.exe` or `bin/macos/dcraw_emu` based on `sys.platform`
- `BASE_OPTIONS` — fixed flags: `-r 1 1 1 1 -M -o 0 -W -4 -T`
- `DEBAYER_ALGORITHMS` — list of `(label, q_value)` tuples driving the GUI dropdown
- `Converter` — wraps binary path + `check_binary()`; `convert_batch()` exists for CLI use but is not called by the GUI

### gui.py
The GUI drives conversion directly without going through `Converter.convert_batch`. Key design:

- **`_run_one(src, out_dir, options, q, cancel, binary)`** — module-level function; runs `dcraw_emu` as a subprocess for one file, posts `_MSG_LOG / _MSG_FILE_START / _MSG_FILE_DONE` typed tuples to a `queue.Queue`
- **`_convert_worker(...)`** — module-level; manages a `ThreadPoolExecutor`, calls `_run_one` per file, posts `_MSG_ALL_DONE` when finished
- **`App._poll()`** — drains the queue every 80 ms via `self.after()`; updates progress bars and log; stops polling on `_MSG_ALL_DONE`
- **Cancel** — `threading.Event` checked at the start of each `_run_one`; already-submitted futures are skipped, in-flight ones complete

### Options passed to dcraw_emu
Full command: `dcraw_emu <BASE_OPTIONS> -q <N> <src_path>`  
Run with `cwd=out_dir` (or `src.parent` if no output folder specified) so dcraw_emu writes the TIFF to the right place.

## Dependencies

No third-party Python packages — only the standard library (`tkinter`, `threading`, `queue`, `subprocess`, `concurrent.futures`). `uv sync` creates the venv and installs the package itself in editable mode.

## Platform notes

- Binary selection is purely `sys.platform == "win32"` vs. everything else (macOS)
- The gitignore excludes `bin/windows/*.exe` and `bin/macos/dcraw_emu` so binaries are never committed
