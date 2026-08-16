"""QEMU-backed firmware behavior check: EXECUTE the built ELF and read the
RTT heartbeat via arm-none-eabi-gdb.

This is the workflow's no-board observation backend: when no debug probe is
attached but QEMU + gdb are present, the debug-observe stage runs the actual
firmware under QEMU (netduinoplus2 = STM32F405, same Cortex-M4 core/family
as the F4 targets) and verifies the RTT heartbeat lands in the ring buffer.
Honest labeling: EMULATED execution, not real hardware — evidence level is
"behavior-emulated", below "behavior-real" (physical probe capture).

Read-only from the host perspective: QEMU runs an emulated machine; no
hardware writes, no flashing, no probe access.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

QEMU_MACHINE = "netduinoplus2"


def find_qemu() -> str:
    """Locate qemu-system-arm: env override, PATH, or the portable xPack zip
    extracted under %TEMP%/qemu-arm (see HANDOFF section 18)."""
    override = os.environ.get("HARDWARE_BUTLER_QEMU_BIN", "")
    if override and Path(override).exists():
        return override
    found = shutil.which("qemu-system-arm")
    if found:
        return found
    pattern = os.path.join(
        os.environ.get("TEMP", ""), "qemu-arm", "*", "bin", "qemu-system-arm.exe"
    )
    for candidate in sorted(glob.glob(pattern), reverse=True):
        if Path(candidate).exists():
            return candidate
    return ""


def find_gdb() -> str:
    """Locate arm-none-eabi-gdb: env override or the PlatformIO toolchain."""
    override = os.environ.get("HARDWARE_BUTLER_ARM_GDB", "")
    if override and Path(override).exists():
        return override
    home = Path.home()
    for pattern in (
        ".platformio/packages/toolchain-gccarmnoneeabi*/bin/arm-none-eabi-gdb.exe",
        ".platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-gdb.exe",
    ):
        for candidate in sorted(home.glob(pattern), reverse=True):
            if candidate.exists():
                return str(candidate)
    return ""


def available() -> bool:
    return bool(find_qemu() and find_gdb())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_gdb_output(out: str) -> dict[str, Any]:
    """Extract the behavior facts from a gdb batch transcript. Pure function
    so the parsing contract is unit-testable without QEMU."""
    task = ""
    heartbeat = ""
    wr_off: int | None = None
    breakpoint_hit = "Breakpoint 1" in out and "app_rtt_puts" in out
    task_match = re.search(r"in (app_\w+_task) \(\)", out)
    if task_match:
        task = task_match.group(1)
    string_match = re.search(r'^.*(0x[0-9a-fA-F]+ <app_rtt_up_storage>):\s*"([^"]*)"', out, re.MULTILINE)
    if string_match:
        heartbeat = string_match.group(2)
    wr_match = re.search(r"<app_rtt_cb\+32>:\s*0x([0-9a-fA-F]+)", out)
    if wr_match:
        wr_off = int(wr_match.group(1), 16)
    ok = bool(breakpoint_hit and task and heartbeat and wr_off)
    return {
        "status": "ok" if ok else "error",
        "breakpoint_hit": breakpoint_hit,
        "task_symbol": task,
        "heartbeat": heartbeat,
        "wr_off": wr_off,
    }


def run_behavior_check(elf: str, *, timeout_s: int = 120, attempts: int = 2) -> dict[str, Any]:
    """Execute `elf` under QEMU and verify the RTT heartbeat write.

    Retries once on transient failures (stale gdb/qemu processes, port
    races) before giving up.

    Returns {"status": "ok|error|skipped", "backend": "qemu", "machine": ...,
    "capture": <heartbeat text actually read from the RTT ring buffer>, ...}.
    """
    result: dict[str, Any] = {"status": "skipped", "backend": "qemu", "reason": "not attempted"}
    for attempt in range(max(1, attempts)):
        result = _run_behavior_check_once(elf, timeout_s=timeout_s)
        if result["status"] != "error":
            return result
    return result


def _run_behavior_check_once(elf: str, *, timeout_s: int) -> dict[str, Any]:
    qemu = find_qemu()
    gdb = find_gdb()
    if not (qemu and gdb):
        return {"status": "skipped", "backend": "qemu", "reason": "qemu or arm-none-eabi-gdb not found"}
    if not Path(elf).exists():
        return {"status": "skipped", "backend": "qemu", "reason": f"elf not found: {elf}"}

    port = _free_port()
    elf_posix = str(elf).replace("\\", "/")  # gdb -ex args must not use backslashes
    qemu_proc = subprocess.Popen(
        [
            qemu,
            "-M", QEMU_MACHINE,
            "-nographic",
            "-monitor", "none",
            "-serial", "none",
            "-kernel", elf_posix,
            "-S",
            "-gdb", f"tcp::{port}",
        ],
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        try:
            gdb_result = subprocess.run(
                [
                    gdb,
                    "-batch",
                    "-ex", "set pagination off",
                    "-ex", f"file {elf_posix}",
                    "-ex", f"target remote localhost:{port}",
                    "-ex", "break app_rtt_puts",
                    "-ex", "continue",
                    "-ex", "finish",
                    "-ex", "x/wx ((char*)&app_rtt_cb)+32",
                    "-ex", "x/s (char*)&app_rtt_up_storage",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "backend": "qemu",
                "machine": QEMU_MACHINE,
                "reason": "gdb session timed out (firmware may not have reached the heartbeat)",
            }
        parsed = parse_gdb_output(gdb_result.stdout + gdb_result.stderr)
        parsed.update({"backend": "qemu", "machine": QEMU_MACHINE, "elf": elf_posix})
        if parsed["status"] == "ok":
            parsed["capture"] = parsed["heartbeat"] + "\n"
        else:
            parsed["capture"] = ""
            parsed["reason"] = "heartbeat not observed under emulation"
        return parsed
    finally:
        qemu_proc.terminate()
        try:
            qemu_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu_proc.kill()
