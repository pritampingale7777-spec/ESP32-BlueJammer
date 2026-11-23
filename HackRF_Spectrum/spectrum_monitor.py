#!/usr/bin/env python3
"""
HackRF spectrum monitor for study and occupancy logging (Windows / Linux).

Runs `hackrf_sweep` and, for each report interval:
  * prints band occupancy: percent of bins above a dB threshold, per band
  * appends every measured bin to a CSV log (timestamp, freq_hz, db)

This is a general monitoring tool. It records what is on the air over time.
It does not track or follow any individual transmission.

Examples:
  python spectrum_monitor.py --log band_log.csv
  python spectrum_monitor.py --start 400 --stop 1000 --threshold -50 --duration 3600

Requirements: HackRF One, hackrf_sweep on PATH, Python 3.9+.
Receive-only.
"""

import argparse
import csv
import queue
import shutil
import sys
import time

from hackrf_spectrum import (
    LNA_STEPS,
    MAX_MHZ,
    MIN_MHZ,
    SweepRunner,
    build_command,
    validate_settings,
)

# Common bands for occupancy reporting (name, start_mhz, stop_mhz)
BANDS = [
    ("FM broadcast", 88, 108),
    ("Air band", 118, 137),
    ("ISM 433", 433, 435),
    ("ISM 868", 863, 870),
    ("ISM 915", 902, 928),
    ("GPS L1", 1565, 1585),
    ("ISM 2.4 GHz", 2400, 2500),
    ("ISM 5.8 GHz", 5725, 5875),
]


def occupancy(bins, lo_mhz, hi_mhz, threshold_db):
    """Return (percent_above_threshold, bin_count) for bins inside [lo, hi] MHz."""
    inside = [db for f_hz, db in bins if lo_mhz * 1e6 <= f_hz < hi_mhz * 1e6]
    if not inside:
        return None, 0
    above = sum(1 for db in inside if db >= threshold_db)
    return 100.0 * above / len(inside), len(inside)


def report(samples, threshold_db, out):
    print(f"--- report {time.strftime('%H:%M:%S')} (threshold {threshold_db} dB) ---", file=out)
    for name, lo, hi in BANDS:
        pct, n = occupancy(samples, lo, hi, threshold_db)
        if pct is None:
            continue  # band outside the scanned range
        print(f"{name:<14} {lo:>5}-{hi:<5} MHz  occupancy {pct:5.1f}%  ({n} bins)", file=out)
    out.flush()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", type=int, default=MIN_MHZ, help="start MHz (default 1)")
    p.add_argument("--stop", type=int, default=MAX_MHZ, help="stop MHz (default 6000)")
    p.add_argument("--bin", type=int, default=1000000, help="bin width Hz (default 1000000)")
    p.add_argument("--lna", type=int, default=16, choices=LNA_STEPS, help="LNA gain dB")
    p.add_argument("--vga", type=int, default=20, help="VGA gain dB (even, 0-62)")
    p.add_argument("--amp", action="store_true", help="enable RF amp")
    p.add_argument("--threshold", type=float, default=-60.0,
                   help="dB threshold for occupancy (uncalibrated; tune to your noise floor)")
    p.add_argument("--interval", type=int, default=30, help="report every N seconds (default 30)")
    p.add_argument("--duration", type=int, default=0, help="stop after N seconds (0 = run until Ctrl+C)")
    p.add_argument("--log", help="CSV file to append timestamp,freq_hz,db rows to")
    args = p.parse_args()

    error = validate_settings(args.start, args.stop, args.bin, args.lna, args.vga)
    if error:
        sys.exit(error)
    exe = shutil.which("hackrf_sweep")
    if exe is None:
        sys.exit("hackrf_sweep not found. Install the HackRF host tools and add them to PATH.")

    cmd = build_command(exe, args.start, args.stop, args.bin, args.lna, args.vga,
                        args.amp, False)  # antenna power always off in this tool
    q = queue.Queue()
    runner = SweepRunner(cmd, q)
    log_fh = None
    writer = None
    if args.log:
        log_fh = open(args.log, "a", newline="")
        writer = csv.writer(log_fh)
        if log_fh.tell() == 0:
            writer.writerow(["timestamp", "freq_hz", "db"])

    samples = []
    t_start = last_report = time.time()
    runner.start()
    print(f"Monitoring {args.start}-{args.stop} MHz, bin {args.bin} Hz. Ctrl+C to stop.")
    try:
        while True:
            try:
                kind, src, payload = q.get(timeout=0.5)
            except queue.Empty:
                kind = None
            if kind == "data":
                now = time.strftime("%Y-%m-%dT%H:%M:%S")
                for f_hz, db in payload:
                    samples.append((f_hz, db))
                    if writer:
                        writer.writerow([now, round(f_hz), db])
            elif kind == "done":
                print(f"hackrf_sweep exited with code {payload}")
                break
            # keep only the latest pass worth of samples for occupancy (cap memory)
            if len(samples) > 200000:
                samples = samples[-100000:]

            if time.time() - last_report >= args.interval:
                report(samples, args.threshold, sys.stdout)
                samples.clear()
                last_report = time.time()
                if log_fh:
                    log_fh.flush()

            if args.duration and time.time() - t_start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()
        if log_fh:
            log_fh.close()
        if samples:
            report(samples, args.threshold, sys.stdout)


if __name__ == "__main__":
    main()
