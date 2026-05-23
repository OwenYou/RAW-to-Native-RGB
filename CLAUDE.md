# CLAUDE.md

## Project

Batch GUI that converts camera RAW files to native RGB TIFF via the `dcraw_emu` binary from LibRaw. The goal is a **lossless, camera-native** output: linear 16-bit, no WB scaling, no colour space conversion.

## Running

```bash
uv run raw_to_rgb
```

## Project layout

```
bin/
  windows/dcraw_emu.exe   # user-supplied; gitignored
  macos/dcraw_emu         # user-supplied; gitignored
raw_to_rgb/
  __main__.py             # entry point — instantiates App and calls mainloop()
  gui.py                  # tkinter GUI (App extends TkinterDnD.Tk)
  converter.py            # binary path resolution, BASE_OPTIONS, DEBAYER_ALGORITHMS
pyproject.toml            # uv/hatchling config, requires-python = ">=3.12"
```

## Architecture

### converter.py
- `binary_path()` — resolves `bin/windows/dcraw_emu.exe` or `bin/macos/dcraw_emu` based on `sys.platform`
- `BASE_OPTIONS` — fixed flags: `-r 1 1 1 1 -M -o 0 -W -4 -T`
- `DEBAYER_ALGORITHMS` — list of `(label, flags)` tuples where `flags` is a `list[str]` of dcraw_emu arguments (e.g. `["-q", "12"]`; No Debayer uses `["-q", "0", "-h"]`)
- `Converter` — wraps binary path + `check_binary()`; `convert_batch()` exists for CLI use but is not called by the GUI

### gui.py
The GUI drives conversion directly without going through `Converter.convert_batch`. Key design:

- **`_run_one(src, out_dir, options, q, cancel, binary)`** — module-level function; runs `dcraw_emu` as a subprocess for one file, posts `_MSG_LOG / _MSG_FILE_START / _MSG_FILE_DONE` typed tuples to a `queue.Queue`
- **`_convert_worker(...)`** — module-level; manages a `ThreadPoolExecutor`, calls `_run_one` per file, posts `_MSG_ALL_DONE` when finished
- **`App._poll()`** — drains the queue every 80 ms via `self.after()`; updates progress bars and log; stops polling on `_MSG_ALL_DONE`
- **Cancel** — `threading.Event` checked at the start of each `_run_one`; already-submitted futures are skipped, in-flight ones complete
- **Auto-retry** — `_MAX_RETRIES = 1`; after all futures complete, any failed files are re-submitted once via `_start_retry()`; listbox rows turn yellow during retry, green on success, red on final failure
- **`App` class** — extends `TkinterDnD.Tk` (not plain `tk.Tk`) to enable drag-and-drop via `tkinterdnd2`

### Non-ASCII path handling (Windows)
`dcraw_emu.exe` uses the ANSI Win32 APIs internally, so paths containing characters outside the system code page (e.g. Chinese/Japanese directory names) are corrupted before the file is opened. `_ascii_working_dir(src)` applies a three-step fallback:

1. **`GetShortPathNameW`** — 8.3 short paths are always ASCII; works when NTFS 8.3 name creation is enabled (Windows default).
2. **Hard-link to a temp dir** — creates a temp directory with a pure-ASCII path on the same drive, hard-links the source file into it (instantaneous, no data copied), runs `dcraw_emu` from there, then moves the output TIFF back to the intended destination using Python's wide Win32 APIs.
3. **Give up** — returns the original path if neither approach works (e.g. hard-link fails cross-device).

`_pending_cleanup` tracks temp dirs; `_atexit_cleanup()` removes any survivors on unclean exit.

### Options passed to dcraw_emu
Full command: `dcraw_emu <BASE_OPTIONS> <debayer_flags> -Z <out_path> <src_path>`  
`-Z <out_path>` is always provided explicitly so the output TIFF lands in the right place regardless of how dcraw_emu resolves the working directory internally. `cwd` is set to the (ASCII-safe) parent of the source file.

## Dependencies

One third-party package: [`tkinterdnd2>=0.4.2`](https://pypi.org/project/tkinterdnd2/) for drag-and-drop support. Everything else is standard library (`tkinter`, `threading`, `queue`, `subprocess`, `concurrent.futures`, `ctypes`). `uv sync` installs all dependencies and the package itself in editable mode.

## Platform notes

- Binary selection is purely `sys.platform == "win32"` vs. everything else (macOS)
- The gitignore excludes `bin/windows/*.exe` and `bin/macos/dcraw_emu` so binaries are never committed
