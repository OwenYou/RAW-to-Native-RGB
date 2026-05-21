import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk
import tkinter as tk

from raw_to_rgb.converter import BASE_OPTIONS, DEBAYER_ALGORITHMS, Converter, RAW_EXTENSIONS

_MSG_LOG        = "log"
_MSG_FILE_START = "file_start"   # payload: name
_MSG_FILE_DONE  = "file_done"    # payload: (done_1based, total, ok, name)
_MSG_ALL_DONE   = "all_done"


# ── Worker ────────────────────────────────────────────────────────────────────

def _run_one(
    src: Path,
    out_dir: Path | None,
    options: list[str],
    q: queue.Queue,
    cancel: threading.Event,
    binary: Path,
) -> tuple[bool, Path]:
    if cancel.is_set():
        q.put((_MSG_LOG, f"[skipped]  {src.name}\n"))
        return False, src

    cwd = out_dir if out_dir is not None else src.parent
    q.put((_MSG_FILE_START, src.name))

    lines: list[str] = [f"── {src.name} ──\n"]
    ok = False
    try:
        cmd = [str(binary)] + options + [str(src)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
        )
        ok = result.returncode == 0
        if result.stderr:
            lines.append(result.stderr.rstrip() + "\n")
        if not ok and result.stdout:
            lines.append(result.stdout.rstrip() + "\n")
        if ok:
            lines.append("  OK\n")
        else:
            msg = f"  [exit {result.returncode}]"
            if result.returncode == -1073741515:  # 0xC0000135 STATUS_DLL_NOT_FOUND
                msg += "  — libraw.dll not found; copy it alongside dcraw_emu.exe into bin/windows/"
            lines.append(msg + "\n")
    except Exception as exc:
        lines.append(f"  EXCEPTION: {exc}\n")

    q.put((_MSG_LOG, "".join(lines)))
    return ok, src


def _convert_worker(
    files: list[Path],
    out_dir: Path | None,
    options: list[str],
    q: queue.Queue,
    cancel: threading.Event,
    max_workers: int,
    binary: Path,
) -> None:
    total = len(files)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = {
            exe.submit(_run_one, src, out_dir, options, q, cancel, binary): src
            for src in files
        }
        for fut in as_completed(futures):
            ok, src = fut.result()
            done += 1
            q.put((_MSG_FILE_DONE, (done, total, ok, src.name)))
    q.put((_MSG_ALL_DONE, None))


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RAW to Native RGB")
        self.minsize(680, 620)
        self._files: list[Path] = []
        self._thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._after_id: str | None = None
        self._in_flight: int = 0
        self._done_count: int = 0
        self._build_ui()
        self._check_binary_on_start()
        self._update_convert_btn()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        PAD = dict(padx=8, pady=4)

        # ── Input files ───────────────────────────────────────────────────────
        frm_files = ttk.LabelFrame(self, text="Input RAW files")
        frm_files.pack(fill="both", expand=False, **PAD)

        btn_bar = ttk.Frame(frm_files)
        btn_bar.pack(fill="x", padx=4, pady=(4, 2))
        ttk.Button(btn_bar, text="Add files…",      command=self._add_files).pack(side="left", padx=(0, 4))
        ttk.Button(btn_bar, text="Remove selected", command=self._remove_selected).pack(side="left", padx=(0, 4))
        ttk.Button(btn_bar, text="Clear all",       command=self._clear_files).pack(side="left")

        list_frm = ttk.Frame(frm_files)
        list_frm.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        vsb = ttk.Scrollbar(list_frm, orient="vertical")
        self._listbox = tk.Listbox(
            list_frm, selectmode="extended", height=6,
            yscrollcommand=vsb.set, activestyle="dotbox",
        )
        vsb.config(command=self._listbox.yview)
        vsb.pack(side="right", fill="y")
        self._listbox.pack(side="left", fill="both", expand=True)

        # ── Output folder ─────────────────────────────────────────────────────
        frm_out = ttk.LabelFrame(self, text="Output folder  (blank = same folder as each source file)")
        frm_out.pack(fill="x", **PAD)

        out_row = ttk.Frame(frm_out)
        out_row.pack(fill="x", padx=4, pady=4)
        self._out_var = tk.StringVar()
        ttk.Entry(out_row, textvariable=self._out_var).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(out_row, text="Browse…", command=self._browse_out).pack(side="left", padx=(0, 4))
        ttk.Button(out_row, text="Clear",   command=lambda: self._out_var.set("")).pack(side="left")

        # ── Options ───────────────────────────────────────────────────────────
        frm_opts = ttk.LabelFrame(self, text="Options")
        frm_opts.pack(fill="x", **PAD)

        g = ttk.Frame(frm_opts)
        g.pack(padx=8, pady=6, anchor="w")

        debayer_labels = [label for label, _ in DEBAYER_ALGORITHMS]
        self._debayer_var = tk.StringVar(value=debayer_labels[0])
        self._jobs_var = tk.IntVar(value=4)

        ttk.Label(g, text="Debayer algorithm (-q):", anchor="e").grid(
            row=0, column=0, sticky="e", padx=(8, 4)
        )
        ttk.Combobox(
            g, textvariable=self._debayer_var, values=debayer_labels,
            state="readonly", width=34,
        ).grid(row=0, column=1, sticky="w", padx=(0, 24), pady=2)

        ttk.Label(g, text="Parallel jobs (1–8):", anchor="e").grid(
            row=0, column=2, sticky="e", padx=(8, 4)
        )
        ttk.Spinbox(g, from_=1, to=8, textvariable=self._jobs_var, width=6).grid(
            row=0, column=3, sticky="w", padx=(0, 8), pady=2
        )

        # ── Convert / Cancel button ───────────────────────────────────────────
        self._convert_btn = ttk.Button(self, text="Convert", command=self._start, width=28)
        self._convert_btn.pack(pady=6)

        # ── Progress ──────────────────────────────────────────────────────────
        frm_prog = ttk.LabelFrame(self, text="Progress")
        frm_prog.pack(fill="x", **PAD)

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(frm_prog, textvariable=self._status_var).pack(anchor="w", padx=6, pady=(4, 0))

        self._cur_bar = ttk.Progressbar(frm_prog, mode="indeterminate", maximum=100, value=0)
        self._cur_bar.pack(fill="x", padx=6, pady=(2, 0))

        overall_row = ttk.Frame(frm_prog)
        overall_row.pack(fill="x", padx=6, pady=(2, 4))
        ttk.Label(overall_row, text="Overall:").pack(side="left", padx=(0, 4))
        self._overall_bar = ttk.Progressbar(overall_row, mode="determinate", maximum=1, value=0)
        self._overall_bar.pack(side="left", fill="x", expand=True)
        self._overall_label = ttk.Label(overall_row, text="0 / 0", width=8, anchor="e")
        self._overall_label.pack(side="left", padx=(4, 0))

        # ── Log ───────────────────────────────────────────────────────────────
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, **PAD)

        _mono = ("Menlo", 10) if sys.platform == "darwin" else ("Consolas", 9)
        self._log = scrolledtext.ScrolledText(
            frm_log, height=8, state="disabled", font=_mono, wrap="word",
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

    # ── File-list helpers ─────────────────────────────────────────────────────

    def _add_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(RAW_EXTENSIONS))
        paths = filedialog.askopenfilenames(
            title="Select RAW files",
            filetypes=[("RAW files", exts), ("All files", "*.*")],
        )
        existing = {str(p) for p in self._files}
        for p in paths:
            if p not in existing:
                self._files.append(Path(p))
                self._listbox.insert(tk.END, Path(p).name)
        self._update_convert_btn()

    def _remove_selected(self) -> None:
        for idx in reversed(self._listbox.curselection()):
            self._listbox.delete(idx)
            del self._files[idx]
        self._update_convert_btn()

    def _clear_files(self) -> None:
        self._listbox.delete(0, tk.END)
        self._files.clear()
        self._update_convert_btn()

    def _browse_out(self) -> None:
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._out_var.set(d)

    def _update_convert_btn(self) -> None:
        n = len(self._files)
        if n == 0:
            self._convert_btn.config(text="Convert", state="disabled")
        else:
            self._convert_btn.config(
                text=f"Convert  {n} file{'s' if n != 1 else ''}",
                state="normal",
            )

    # ── Binary check ──────────────────────────────────────────────────────────

    def _check_binary_on_start(self) -> None:
        converter = Converter()
        if not converter.check_binary():
            self._log_append(f"[WARNING] dcraw_emu binary not found at:\n  {converter.binary}\n")
            self._log_append("Place the binary in the appropriate bin/ subfolder before converting.\n")
        else:
            self._log_append(f"Binary found: {converter.binary}\n")

    # ── Conversion control ────────────────────────────────────────────────────

    def _build_options(self) -> list[str]:
        label = self._debayer_var.get()
        q_value = next(v for lbl, v in DEBAYER_ALGORITHMS if lbl == label)
        return BASE_OPTIONS + ["-q", q_value]

    def _start(self) -> None:
        if not self._files:
            return

        out_str = self._out_var.get().strip()
        out_dir = Path(out_str) if out_str else None
        if out_dir is not None and not out_dir.is_dir():
            self._log_append(f"[ERROR] Output folder does not exist:\n  {out_dir}\n")
            return

        converter = Converter()
        if not converter.check_binary():
            self._log_append(f"[ERROR] dcraw_emu not found at: {converter.binary}\n")
            return

        options = self._build_options()
        jobs = max(1, min(8, int(self._jobs_var.get())))
        n = len(self._files)

        self._overall_bar.config(maximum=n, value=0)
        self._overall_label.config(text=f"0 / {n}")
        self._cur_bar.config(mode="indeterminate", value=0)
        self._cur_bar.start(12)
        self._status_var.set(f"Starting  ({jobs} parallel job{'s' if jobs != 1 else ''})…")
        self._in_flight = 0
        self._done_count = 0
        self._log_clear()
        self._convert_btn.config(text="Cancel", command=self._cancel, state="normal")
        self._cancel_event.clear()

        self._thread = threading.Thread(
            target=_convert_worker,
            args=(list(self._files), out_dir, options,
                  self._queue, self._cancel_event, jobs, converter.binary),
            daemon=True,
        )
        self._thread.start()
        self._after_id = self.after(80, self._poll)

    def _cancel(self) -> None:
        self._cancel_event.set()
        self._convert_btn.config(text="Cancelling…", state="disabled")

    def _poll(self) -> None:
        total = len(self._files)
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == _MSG_LOG:
                    self._log_append(payload)
                elif kind == _MSG_FILE_START:
                    self._in_flight += 1
                    self._status_var.set(
                        f"  {self._in_flight} in flight  |  {self._done_count} / {total} done"
                    )
                elif kind == _MSG_FILE_DONE:
                    done, tot, ok, name = payload
                    self._in_flight = max(0, self._in_flight - 1)
                    self._done_count = done
                    self._overall_bar["value"] = done
                    self._overall_label.config(text=f"{done} / {tot}")
                    mark = "✓" if ok else "✗"
                    self._status_var.set(
                        f"  {mark} {name}  |  {self._in_flight} in flight  |  {done} / {tot} done"
                    )
                elif kind == _MSG_ALL_DONE:
                    self._on_done()
                    return
        except queue.Empty:
            pass
        self._after_id = self.after(80, self._poll)

    def _on_done(self) -> None:
        self._cur_bar.stop()
        self._cur_bar.config(mode="determinate", value=100)
        n = len(self._files)
        self._status_var.set(f"Done — {n} file{'s' if n != 1 else ''} processed.")
        self._convert_btn.config(
            text=f"Convert  {n} file{'s' if n != 1 else ''}",
            command=self._start,
            state="normal",
        )
        self._after_id = None

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log_append(self, text: str) -> None:
        self._log.config(state="normal")
        self._log.insert(tk.END, text)
        self._log.see(tk.END)
        self._log.config(state="disabled")

    def _log_clear(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", tk.END)
        self._log.config(state="disabled")
