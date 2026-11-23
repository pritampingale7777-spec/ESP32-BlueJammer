#!/usr/bin/env python3
"""
Flash ESP32-BlueJammer firmware .bin files to an ESP32 over USB serial.

Wraps esptool (https://github.com/espressif/esptool) so you don't have to
remember flash offsets. Works with the binaries in this repository's
Firmware_Files/ folder.

Usage examples:
  # List available firmware images
  python flash_firmware.py --list

  # Flash the app image only (most common)
  python flash_firmware.py --port /dev/ttyUSB0 --firmware Generic/WiFi_14_CH.ino.bin

  # Flash bootloader + partition table + app (full image set)
  python flash_firmware.py --port COM3 --firmware OLED/Bluetooth_80_CH.ino.bin --full

Requirements:
  pip install esptool pyserial
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIRMWARE_DIR = SCRIPT_DIR / "Firmware_Files"
BOOTLOADER_DIR = FIRMWARE_DIR / "Bootloader&Partitions"
BOOTLOADER_BIN = BOOTLOADER_DIR / "ESP32-BlueJammer.bootloader.bin"
PARTITIONS_BIN = BOOTLOADER_DIR / "ESP32-BlueJammer.partitions.bin"

# Standard ESP32 (Arduino-style) flash offsets
BOOTLOADER_OFFSET = "0x1000"
PARTITIONS_OFFSET = "0x8000"
APP_OFFSET = "0x10000"


def find_firmware_files() -> list[Path]:
    """Return every *.bin application image under Firmware_Files/."""
    return sorted(
        p for p in FIRMWARE_DIR.rglob("*.ino.bin")
        if BOOTLOADER_DIR not in p.parents
    )


def resolve_firmware(name: str) -> Path:
    """Accept either a path relative to Firmware_Files/ or a bare file name."""
    candidate = (FIRMWARE_DIR / name)
    if candidate.is_file():
        return candidate
    matches = [p for p in find_firmware_files() if p.name == name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(
            f"Ambiguous firmware name '{name}'. Use a path such as "
            f"{matches[0].relative_to(FIRMWARE_DIR)}"
        )
    raise SystemExit(f"Firmware '{name}' not found. Run with --list to see options.")


def build_esptool_command(port: str, baud: int, images: list[tuple[str, Path]]) -> list[str]:
    cmd = [sys.executable, "-m", "esptool", "--chip", "esp32", "--port", port,
           "--baud", str(baud), "--before", "default-reset",
           "--after", "hard-reset", "write-flash", "-z"]
    for offset, path in images:
        cmd += [offset, str(path)]
    return cmd


def run(cmd: list[str]) -> None:
    print("> " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"esptool failed with exit code {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true",
                        help="list available firmware images and exit")
    parser.add_argument("--port", help="serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--firmware", help="firmware file (path under Firmware_Files/ or bare name)")
    parser.add_argument("--baud", type=int, default=921600, help="baud rate (default: 921600)")
    parser.add_argument("--full", action="store_true",
                        help="also flash bootloader and partition table (overwrites them)")
    parser.add_argument("--erase", action="store_true",
                        help="erase the entire flash before writing (wipes everything)")
    args = parser.parse_args()

    if args.list:
        for p in find_firmware_files():
            print(p.relative_to(FIRMWARE_DIR).as_posix())
        return

    if not args.port or not args.firmware:
        parser.error("--port and --firmware are required (or use --list)")

    if shutil.which("esptool") is None and subprocess.run(
            [sys.executable, "-m", "esptool", "version"],
            capture_output=True).returncode != 0:
        raise SystemExit("esptool is not installed. Run: pip install esptool pyserial")

    app = resolve_firmware(args.firmware)
    print(f"Firmware: {app.relative_to(SCRIPT_DIR).as_posix()}")

    if args.erase:
        confirm = input("This erases the ENTIRE flash. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            raise SystemExit("Aborted.")
        run([sys.executable, "-m", "esptool", "--chip", "esp32", "--port", args.port,
             "--baud", str(args.baud), "erase-flash"])

    images: list[tuple[str, Path]] = []
    if args.full:
        for label, path in (("bootloader", BOOTLOADER_BIN), ("partitions", PARTITIONS_BIN)):
            if not path.is_file():
                raise SystemExit(f"Missing {label} image: {path}")
        images += [(BOOTLOADER_OFFSET, BOOTLOADER_BIN), (PARTITIONS_OFFSET, PARTITIONS_BIN)]
    images.append((APP_OFFSET, app))

    run(build_esptool_command(args.port, args.baud, images))
    print("Done. The ESP32 has been reset and should boot the new firmware.")


if __name__ == "__main__":
    main()
