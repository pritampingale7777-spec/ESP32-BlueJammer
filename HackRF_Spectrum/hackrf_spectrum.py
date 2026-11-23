#!/usr/bin/env python3
"""
HackRF One full-spectrum scanner GUI (1 MHz - 6 GHz).

Runs the HackRF host tool `hackrf_sweep` and draws the result live:
  * live trace (blue) and max-hold trace (orange)
  * top-15 peak table
  * CSV export (freq_hz, latest_db, maxhold_db)

Receive-only: this program never transmits.

Requirements:
  * HackRF One and the HackRF host tools (`hackrf_sweep` on PATH)
  * Python 3.9+ with Tkinter

Note: HackRF One tunes from about 1 MHz to 6 GHz. A 1 Hz start is not
possible in hardware, so the lowest start frequency is 1 MHz.
Levels are relative (uncalibrated) dB as reported by hackrf_sweep.
"""

import csv
import math
import queue
import shutil
import subprocess
import threading

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # GUI unavailable; pure helpers below still work
    tk = None

MIN_MHZ = 1
MAX_MHZ = 6000
MIN_BIN_HZ = 2445          # hackrf_sweep minimum bin width
LNA_STEPS = (0, 8, 16, 24, 32, 40)
VGA_STEPS = tuple(range(0, 63, 2))
SWEEP_HEADER_FIELDS = 6    # date, time, hz_low, hz_high, bin_width, num_samples
DB_TOP, DB_BOTTOM = 0, -110


def parse_sweep_line(line):
    """Parse one hackrf_sweep CSV line into a list of (freq_hz, db) pairs.

    Returns an empty list for lines that are not sweep data.
    """
    parts = [p.strip() for p in line.strip().split(",")]
    if len(parts) <= SWEEP_HEADER_FIELDS:
        return []
    try:
        hz_low = int(parts[2])
        bin_width = float(parts[4])
        dbs = [float(v) for v in parts[SWEEP_HEADER_FIELDS:] if v]
    except ValueError:
        return []
    return [(hz_low + (i + 0.5) * bin_width, db) for i, db in enumerate(dbs)]


def build_command(exe, start_mhz, stop_mhz, bin_hz, lna, vga, amp, antenna_power):
    """Build the hackrf_sweep argument list."""
    return [
        exe,
        "-f", f"{start_mhz}:{stop_mhz}",
        "-w", str(bin_hz),
        "-l", str(lna),
        "-g", str(vga),
        "-a", "1" if amp else "0",
        "-p", "1" if antenna_power else "0",
    ]


def validate_settings(start_mhz, stop_mhz, bin_hz, lna, vga):
    """Return an error message, or None if the settings are valid."""
    if not (MIN_MHZ <= start_mhz < stop_mhz <= MAX_MHZ):
        return f"Frequency range must satisfy {MIN_MHZ} <= start < stop <= {MAX_MHZ} MHz."
    if bin_hz < MIN_BIN_HZ:
        return f"Bin width must be at least {MIN_BIN_HZ} Hz."
    if lna not in LNA_STEPS:
        return f"LNA gain must be one of {LNA_STEPS}."
    if vga not in VGA_STEPS:
        return "VGA gain must be an even number from 0 to 62."
    return None


def nice_step(span):
    """Pick a 1/2/5 x 10^n tick spacing giving roughly 8 ticks across span."""
    raw = max(span / 8.0, 1e-9)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def pick_peaks(data, n=15, min_sep_khz=10000):
    """Return the n strongest (freq_khz, db) peaks, skipping bins near a stronger peak."""
    chosen = []
    for k, db in sorted(data.items(), key=lambda kv: kv[1], reverse=True):
        if all(abs(k - ck) >= min_sep_khz for ck, _ in chosen):
            chosen.append((k, db))
            if len(chosen) == n:
                break
    return chosen


class SweepRunner:
    """Runs hackrf_sweep in a subprocess and reads its output on a thread."""

    def __init__(self, cmd, out_queue):
        self.cmd = cmd
        self.q = out_queue
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge so stderr can never block the pipe
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            bins = parse_sweep_line(line)
            if bins:
                self.q.put(("data", self, bins))
            elif line.strip():
                self.q.put(("log", self, line.strip()))
        self.q.put(("done", self, self.proc.wait()))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


if tk is not None:

    class App(tk.Tk):
        PLOT_W, PLOT_H = 1000, 420
        PAD_L, PAD_R, PAD_T, PAD_B = 60, 20, 16, 30

        def __init__(self):
            super().__init__()
            self.title("HackRF Full-Spectrum Scanner (1 MHz - 6 GHz)")
            self.geometry("1280x760")
            self.runner = None
            self.q = queue.Queue()
            self.latest = {}    # freq_khz -> db (live)
            self.maxhold = {}   # freq_khz -> db (max hold)
            self.range_mhz = (MIN_MHZ, MAX_MHZ)
            self.status = tk.StringVar(value="Idle. Press Start.")
            self._build_controls()
            self._build_plot()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self.after(50, self._poll)
            self.after(150, self._redraw)

        # ---- layout -------------------------------------------------------
        def _build_controls(self):
            top = ttk.Frame(self, padding=8)
            top.pack(side=tk.TOP, fill=tk.X)

            self.start_var = tk.StringVar(value=str(MIN_MHZ))
            self.stop_var = tk.StringVar(value=str(MAX_MHZ))
            self.bin_var = tk.StringVar(value="1000000")
            self.lna_var = tk.StringVar(value="16")
            self.vga_var = tk.StringVar(value="20")
            self.amp_var = tk.BooleanVar(value=False)
            self.ant_var = tk.BooleanVar(value=False)

            fields = [
                ("Start (MHz)", self.start_var, 8),
                ("Stop (MHz)", self.stop_var, 8),
                ("Bin (Hz)", self.bin_var, 10),
            ]
            for col, (label, var, width) in enumerate(fields):
                ttk.Label(top, text=label).grid(row=0, column=col * 2, sticky="w", padx=4)
                ttk.Entry(top, textvariable=var, width=width).grid(row=0, column=col * 2 + 1, padx=4)

            ttk.Label(top, text="LNA").grid(row=0, column=6, sticky="w", padx=4)
            ttk.Combobox(top, textvariable=self.lna_var, values=list(LNA_STEPS),
                         state="readonly", width=4).grid(row=0, column=7, padx=4)
            ttk.Label(top, text="VGA").grid(row=0, column=8, sticky="w", padx=4)
            ttk.Spinbox(top, textvariable=self.vga_var, from_=0, to=62, increment=2,
                        width=4).grid(row=0, column=9, padx=4)

            ttk.Checkbutton(top, text="RF amp (+14 dB)", variable=self.amp_var).grid(
                row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 0))
            ttk.Checkbutton(top, text="Antenna power 3.3 V (bias-tee, off unless needed)",
                            variable=self.ant_var).grid(
                row=1, column=2, columnspan=5, sticky="w", padx=4, pady=(6, 0))

            self.start_btn = ttk.Button(top, text="Start", command=self._start)
            self.start_btn.grid(row=1, column=7, padx=4, pady=(6, 0))
            self.stop_btn = ttk.Button(top, text="Stop", command=self._stop, state="disabled")
            self.stop_btn.grid(row=1, column=8, padx=4, pady=(6, 0))
            ttk.Button(top, text="Reset max-hold", command=self._reset).grid(
                row=1, column=9, padx=4, pady=(6, 0))
            ttk.Button(top, text="Save CSV", command=self._save).grid(
                row=1, column=10, padx=4, pady=(6, 0))

            ttk.Label(self, textvariable=self.status, anchor="w", padding=(8, 2)).pack(
                side=tk.TOP, fill=tk.X)

        def _build_plot(self):
            body = ttk.Frame(self, padding=8)
            body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.canvas = tk.Canvas(body, width=self.PLOT_W, height=self.PLOT_H,
                                    bg="#101418", highlightthickness=0)
            self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            side = ttk.Frame(body, padding=(8, 0, 0, 0), width=270)
            side.pack(side=tk.RIGHT, fill=tk.Y)
            side.pack_propagate(False)
            ttk.Label(side, text="Top peaks (max-hold)").pack(anchor="w")
            self.tree = ttk.Treeview(side, columns=("freq", "db"), show="headings")
            self.tree.heading("freq", text="MHz")
            self.tree.heading("db", text="dB")
            self.tree.column("freq", width=130, anchor="e", stretch=False)
            self.tree.column("db", width=80, anchor="e", stretch=False)
            self.tree.pack(fill=tk.BOTH, expand=True)

        # ---- actions ------------------------------------------------------
        def _start(self):
            if self.runner is not None:
                return
            try:
                start = int(float(self.start_var.get()))
                stop = int(float(self.stop_var.get()))
                bin_hz = int(float(self.bin_var.get()))
                lna = int(self.lna_var.get())
                vga = int(float(self.vga_var.get()))
            except ValueError:
                messagebox.showerror("Invalid input", "All settings must be numbers.")
                return
            error = validate_settings(start, stop, bin_hz, lna, vga)
            if error:
                messagebox.showerror("Invalid settings", error)
                return
            exe = shutil.which("hackrf_sweep")
            if exe is None:
                messagebox.showerror(
                    "hackrf_sweep not found",
                    "Install the HackRF host tools and make sure hackrf_sweep is on PATH.")
                return
            if self.ant_var.get() and not messagebox.askyesno(
                    "Antenna power",
                    "Antenna power sends 3.3 V to the antenna port. "
                    "Continue only if your antenna or LNA needs it. Enable?"):
                return

            cmd = build_command(exe, start, stop, bin_hz, lna, vga,
                                self.amp_var.get(), self.ant_var.get())
            self.range_mhz = (start, stop)
            self.latest.clear()
            self.runner = SweepRunner(cmd, self.q)
            try:
                self.runner.start()
            except OSError as exc:
                self.runner = None
                messagebox.showerror("Failed to start", str(exc))
                return
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status.set("Scanning...")

        def _stop(self):
            if self.runner is not None:
                self.runner.stop()
                self.status.set("Stopping...")

        def _reset(self):
            self.maxhold.clear()
            self.latest.clear()

        def _save(self):
            if not self.maxhold and not self.latest:
                messagebox.showinfo("Nothing to save", "No sweep data yet.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                initialfile="hackrf_sweep.csv")
            if not path:
                return
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["freq_hz", "latest_db", "maxhold_db"])
                for k in sorted(set(self.latest) | set(self.maxhold)):
                    writer.writerow([k * 1000, self.latest.get(k, ""), self.maxhold.get(k, "")])
            self.status.set(f"Saved {path}")

        def _on_close(self):
            if self.runner is not None:
                self.runner.stop()
            self.destroy()

        # ---- background message pump ---------------------------------------
        def _poll(self):
            try:
                while True:
                    kind, runner, payload = self.q.get_nowait()
                    if runner is not self.runner:
                        continue  # message from an old, stopped run
                    if kind == "data":
                        for freq_hz, db in payload:
                            k = round(freq_hz / 1000)
                            self.latest[k] = db
                            if db > self.maxhold.get(k, -math.inf):
                                self.maxhold[k] = db
                    elif kind == "log":
                        self.status.set(payload[:200])
                    elif kind == "done":
                        self.runner = None
                        self.start_btn.config(state="normal")
                        self.stop_btn.config(state="disabled")
                        self.status.set(f"Stopped (hackrf_sweep exit code {payload})")
            except queue.Empty:
                pass
            self.after(50, self._poll)

        # ---- drawing ------------------------------------------------------
        def _redraw(self):
            c = self.canvas
            c.delete("all")
            w, h = c.winfo_width(), c.winfo_height()
            if w < 50 or h < 50:
                w, h = self.PLOT_W, self.PLOT_H
            x0, x1 = self.PAD_L, w - self.PAD_R
            y0, y1 = self.PAD_T, h - self.PAD_B
            lo, hi = self.range_mhz
            span = hi - lo

            def xy(khz, db):
                x = x0 + (khz / 1000.0 - lo) / span * (x1 - x0)
                db = min(max(db, DB_BOTTOM), DB_TOP)
                y = y0 + (DB_TOP - db) / (DB_TOP - DB_BOTTOM) * (y1 - y0)
                return x, y

            # dB grid
            for db in range(DB_TOP, DB_BOTTOM - 1, -20):
                _, y = xy(lo * 1000, db)
                c.create_line(x0, y, x1, y, fill="#26313c")
                c.create_text(x0 - 6, y, text=f"{db}", fill="#8a99a8", anchor="e")

            # frequency grid
            step = nice_step(span)
            f = math.ceil(lo / step) * step
            while f <= hi:
                x, _ = xy(f * 1000, DB_BOTTOM)
                c.create_line(x, y0, x, y1, fill="#26313c")
                label = f"{f/1000:g} GHz" if f >= 1000 else f"{f:g} MHz"
                c.create_text(x, y1 + 12, text=label, fill="#8a99a8")
                f += step

            # traces
            for data, color in ((self.maxhold, "#ff9e3b"), (self.latest, "#4fc3f7")):
                pts = sorted(data.items())
                if len(pts) >= 2 and lo * 1000 <= pts[0][0] <= hi * 1000:
                    coords = []
                    for k, db in pts:
                        if lo * 1000 <= k <= hi * 1000:
                            coords.extend(xy(k, db))
                    if len(coords) >= 4:
                        c.create_line(*coords, fill=color, width=1)

            # peaks table
            top = pick_peaks(self.maxhold)
            self.tree.delete(*self.tree.get_children())
            for k, db in top:
                self.tree.insert("", "end", values=(f"{k/1000:.3f}", f"{db:.1f}"))

            self.after(150, self._redraw)


def main():
    if tk is None:
        raise SystemExit("Tkinter is not available in this Python installation.")
    App().mainloop()


if __name__ == "__main__":
    main()
