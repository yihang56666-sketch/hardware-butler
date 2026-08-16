"""Tests: FreeRTOS codegen is kept on the PlatformIO backend for stm32cube.

Previously the firmware-plan stage downgraded RTOS codegen to bare-metal
whenever PlatformIO was available, because the stock stm32cube builder does
not compile the framework-bundled FreeRTOS middleware. Now the STM32 adapter
ships a generated pio_freertos.py pre-script, so RTOS intent survives the
PlatformIO build backend; families without that support still downgrade.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "tools")

import vendor_adapters  # noqa: E402
import workflow_runner as wr  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_fixture(fixture: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, dst)
    return dst


def _prepared_state(project: Path, family: str) -> dict:
    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink", context=ctx)
    for sid in ("requirement-parse", "chip-selection", "datasheet-collect", "cubemx-config"):
        stage = next(s for s in state["stages"] if s["id"] == sid)
        stage["status"] = "completed"
        stage["evidence"] = {"placeholder": True}
    req = next(s for s in state["stages"] if s["id"] == "requirement-parse")
    req["evidence"] = {
        "parsed_requirements": {
            "feature": "led-blink",
            "pin": "PD12",
            "function": "gpio-output",
        }
    }
    chip = next(s for s in state["stages"] if s["id"] == "chip-selection")
    chip["evidence"] = {
        "selected_part": "STM32F407VGT6",
        "backends": {
            "vendor_adapter": {"family": family},
            "backends": {"build": "platformio", "flash": "probe-rs", "observe": "serial"},
        },
    }
    return state


def test_firmware_plan_keeps_rtos_when_platformio_supports_freertos(
    cubemx_basic_fixture: Path, tmp_path: Path
) -> None:
    """stm32 + pio available: RTOS codegen stays on (freertos.c thread main,
    FreeRTOSConfig.h), no downgrade note."""
    project = _copy_fixture(
        cubemx_basic_fixture, tmp_path / "rtos-kept" / "project"
    )
    state = _prepared_state(project, "stm32")
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    with patch.object(adapter, "find_pio", return_value="C:/fake/pio.exe"):
        result = wr._stage_firmware_plan(project, state["context"], state)
    assert result.status == "completed"
    patch_ev = result.evidence["firmware_patch"]
    assert patch_ev["rtos_codegen"] is True
    assert patch_ev["rtos_note"] == ""
    # RTOS scaffold artifacts actually written
    freertos_cfg = project / "Core" / "Inc" / "FreeRTOSConfig.h"
    assert freertos_cfg.exists(), "RTOS codegen must produce FreeRTOSConfig.h"
    main_c = project / "Core" / "Src" / "main.c"
    assert "osThreadCreate" in main_c.read_text(encoding="utf-8")


def test_firmware_plan_downgrades_rtos_for_unsupported_pio_family(
    cubemx_basic_fixture: Path, tmp_path: Path
) -> None:
    """esp32 + pio available: codegen downgrades to bare-metal with a note
    (arduino framework has its own FreeRTOS but that codegen path is not
    wired)."""
    project = _copy_fixture(
        cubemx_basic_fixture, tmp_path / "rtos-downgraded" / "project"
    )
    state = _prepared_state(project, "esp32")
    adapter = vendor_adapters.get_adapter("esp32")
    assert adapter is not None
    with patch.object(adapter, "find_pio", return_value="C:/fake/pio.exe"):
        result = wr._stage_firmware_plan(project, state["context"], state)
    assert result.status == "completed"
    patch_ev = result.evidence["firmware_patch"]
    assert patch_ev["rtos_codegen"] is False
    assert "downgraded" in patch_ev["rtos_note"]
    assert not (project / "Core" / "Inc" / "FreeRTOSConfig.h").exists()


def test_firmware_plan_rtos_when_no_pio_uses_adapter_native(
    cubemx_basic_fixture: Path, tmp_path: Path
) -> None:
    """No pio anywhere: RTOS codegen on (native toolchain path, unchanged
    pre-existing behavior)."""
    project = _copy_fixture(
        cubemx_basic_fixture, tmp_path / "rtos-native" / "project"
    )
    state = _prepared_state(project, "stm32")
    with patch("shutil.which", return_value=None):
        with patch("pathlib.Path.exists", return_value=False):
            result = wr._stage_firmware_plan(project, state["context"], state)
    assert result.status == "completed"
    assert result.evidence["firmware_patch"]["rtos_codegen"] is True


def test_stage_build_passes_rtos_to_platformio_backend(
    cubemx_basic_fixture: Path, tmp_path: Path
) -> None:
    """The build stage must forward the firmware-plan RTOS decision in the
    PlatformIO build ctx so the auto-generated ini wires pio_freertos.py."""
    project = _copy_fixture(
        cubemx_basic_fixture, tmp_path / "build-ctx" / "project"
    )
    state = _prepared_state(project, "stm32")
    fw = next(s for s in state["stages"] if s["id"] == "firmware-plan")
    fw["status"] = "completed"
    fw["evidence"] = {"firmware_patch": {"rtos_codegen": True}}
    captured: dict[str, object] = {}
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None

    def fake_build(self: object, ctx: dict) -> list[str]:  # noqa: ANN001
        captured.update(ctx)
        return ["/fake/pio", "run", "-d", str(project)]

    with patch.object(vendor_adapters.VendorAdapter, "build_via_platformio", new=fake_build):
        result = wr._stage_build(project, state["context"], state)
    assert result.status == "completed"
    assert captured.get("rtos") is True


# --- Real compile (no board): full RTOS chain through actual PlatformIO ---
# Gated behind HARDWARE_BUTLER_REAL_COMPILE=1 so the normal suite never
# spawns toolchains; run manually:
#   HARDWARE_BUTLER_REAL_COMPILE=1 pytest tests/unit/test_workflow_rtos_codegen.py -q --no-cov

_PIO_CANDIDATES = [
    shutil.which("pio") or "",
    str(REPO_ROOT / ".venv" / "Scripts" / "pio.exe"),
]


@pytest.mark.enable_platformio
@pytest.mark.skipif(
    not os.environ.get("HARDWARE_BUTLER_REAL_COMPILE"),
    reason="set HARDWARE_BUTLER_REAL_COMPILE=1 to run real toolchain compiles",
)
@pytest.mark.skipif(
    not any(Path(p).exists() for p in _PIO_CANDIDATES if p),
    reason="PlatformIO not installed",
)
def test_real_platformio_freertos_compile_e2e(cubemx_basic_fixture: Path) -> None:
    """Fixture .ioc (FreeRTOS enabled) -> firmware-plan keeps RTOS -> scaffold
    writes osThread main + FreeRTOSConfig.h -> pio run (stm32cube framework +
    generated pio_freertos.py) produces a firmware.elf that actually contains
    the FreeRTOS kernel + CMSIS-RTOS objects."""
    import subprocess

    # safe_io refuses writes outside the repo, so stage inside .tmp-wf-tests
    # (gitignored); PlatformIO itself builds in an ASCII temp staging dir.
    project = _copy_fixture(
        cubemx_basic_fixture, REPO_ROOT / ".tmp-wf-tests" / "real-freertos" / "project"
    )
    state = _prepared_state(project, "stm32")
    adapter = vendor_adapters.get_adapter("stm32")
    assert adapter is not None
    pio = next(p for p in _PIO_CANDIDATES if p and Path(p).exists())
    with patch.object(adapter, "find_pio", return_value=pio):
        result = wr._stage_firmware_plan(project, state["context"], state)
        assert result.status == "completed"
        assert result.evidence["firmware_patch"]["rtos_codegen"] is True
        # Argv list straight from the adapter (deterministic tokens, no shell).
        argv = adapter.build_via_platformio(
            {
                "project_root": str(project),
                "part": "STM32F407VGT6",
                "rtos": True,
            }
        )
    assert argv, "pio command expected"
    assert Path(argv[0]).exists(), argv[0]
    build_root = Path(argv[-1])
    ini = (build_root / "platformio.ini").read_text(encoding="utf-8")
    assert "extra_scripts = pre:pio_freertos.py" in ini
    assert (build_root / "pio_freertos.py").exists()

    proc = subprocess.run(
        [str(part) for part in argv],
        shell=False,
        capture_output=True,
        text=True,
        timeout=420,
    )
    log = proc.stdout + proc.stderr
    assert proc.returncode == 0, log[-4000:]

    build_out = build_root / ".pio" / "build"
    elfs = list(build_out.rglob("firmware.elf"))
    assert elfs, "expected firmware.elf in PlatformIO build output"
    # The stm32cube builder links without a map file, so verify FreeRTOS
    # linkage from the ELF symbol table + the compiled object set.
    elf_bytes = elfs[0].read_bytes()
    for symbol in (b"osThreadCreate", b"osKernelStart", b"vApplicationStackOverflowHook"):
        assert symbol in elf_bytes, f"{symbol.decode()} missing from linked ELF"
    # RTT observability: the control block magic must be in the image so
    # probe-rs/pyOCD can discover it by RAM scan, and the heartbeat call
    # must be linked.
    assert b"SEGGER RTT" in elf_bytes, "RTT control block magic missing from ELF"
    assert b"app_rtt_puts" in elf_bytes, "RTT heartbeat helper missing from ELF"
    objs = {p.name for p in (build_out.rglob("*.o"))}
    assert "tasks.o" in objs, "FreeRTOS kernel not compiled"
    assert "cmsis_os.o" in objs, "CMSIS-RTOS v1 wrapper not compiled"
    assert "port.o" in objs, "FreeRTOS GCC port not compiled"
    assert "heap_4.o" in objs, "FreeRTOS heap_4 allocator not compiled"
