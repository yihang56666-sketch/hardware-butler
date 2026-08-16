"""Tests for firmware_project_scaffold: closing the generate->compile gap.

The scaffold replaces stub main.c with one that calls the generated app
module, creates main.h when missing, and integrates into real CubeMX
USER CODE blocks instead of overwriting them.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import firmware_project_scaffold as fps  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
TMP = REPO_ROOT / "tests" / "tmp" / "firmware-scaffold"


def copy_fixture(name: str) -> Path:
    target = TMP / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(FIXTURE, target)
    return target


def test_classify_main_c_stub_cubemx_custom() -> None:
    assert fps.classify_main_c("int main(void) {\n    while (1) {\n    }\n}\n") == "stub"
    assert fps.classify_main_c("/* USER CODE BEGIN 4 */\n") == "cubemx"
    assert fps.classify_main_c("int main(void) {\n    MX_GPIO_Init();\n    while (1) {}\n}\n") == "custom"
    long_custom = "int main(void) {\n    setup();\n" + "    do_stuff();\n" * 60 + "}\n"
    assert fps.classify_main_c(long_custom) == "custom"


def test_hal_header_for_part() -> None:
    assert fps.hal_header_for_part("STM32F407VGTx") == "stm32f4xx_hal.h"
    assert fps.hal_header_for_part("STM32L476RGT6") == "stm32l4xx_hal.h"
    try:
        fps.hal_header_for_part("ESP32")
    except ValueError:
        pass
    else:
        raise AssertionError("ESP32 should not map to an STM32 HAL header")


def test_ensure_compilable_replaces_stub_and_creates_main_h() -> None:
    project = copy_fixture("stub")
    result = fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink")

    assert result["status"] == "ok"
    assert result["main_c_class"] == "stub"
    written = {Path(p).name for p in result["files_written"]}
    assert {"main.c", "main.h"} <= written
    main_c = (project / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
    assert '#include "app_led_blink.h"' in main_c
    assert "app_led_blink_init();" in main_c
    assert "app_led_blink_task(" in main_c
    assert "HAL_Init();" in main_c
    main_h = (project / "Core" / "Inc" / "main.h").read_text(encoding="utf-8")
    assert 'stm32f4xx_hal.h' in main_h


def test_ensure_compilable_integrates_into_cubemx_user_code_blocks() -> None:
    project = copy_fixture("cubemx")
    main_c = project / "Core" / "Src" / "main.c"
    main_c.write_text(
        "/* Includes */\n"
        '/* USER CODE BEGIN Includes */\n'
        '/* USER CODE END Includes */\n'
        "int main(void) {\n"
        "    HAL_Init();\n"
        "    /* USER CODE BEGIN 2 */\n"
        "    /* USER CODE END 2 */\n"
        "    while (1) {\n"
        "    /* USER CODE BEGIN 4 */\n"
        "    /* USER CODE END 4 */\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    result = fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink")

    assert result["status"] == "ok"
    assert result["main_c_class"] == "cubemx"
    updated = main_c.read_text(encoding="utf-8")
    assert '#include "app_led_blink.h"' in updated
    assert "app_led_blink_init();" in updated
    assert "app_led_blink_task(NULL);" in updated
    # Original structure preserved
    assert "HAL_Init();" in updated
    assert updated.count("USER CODE BEGIN 2") == 1


def test_ensure_compilable_leaves_custom_main_untouched() -> None:
    project = copy_fixture("custom")
    main_c = project / "Core" / "Src" / "main.c"
    original = (
        "int main(void) {\n    MX_GPIO_Init();\n"
        "    start_application();\n    for (;;) {}\n}\n"
    )
    main_c.write_text(original, encoding="utf-8")
    result = fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink")

    assert result["status"] == "ok"
    assert result["main_c_class"] == "custom"
    assert main_c.read_text(encoding="utf-8") == original
    assert any("left untouched" in action for action in result["actions"])


def test_ensure_compilable_requires_part() -> None:
    project = copy_fixture("nopart")
    result = fps.ensure_compilable(project, part="", module="led_blink")
    assert result["status"] == "blocked-needs-input"
    assert "part" in result["error"]


# --- RTOS (FreeRTOS / CMSIS-RTOS v1) scaffold support ---

def test_render_main_c_rtos_creates_freertos_thread() -> None:
    src = fps.render_main_c("led_blink", rtos=True)
    assert '#include "cmsis_os.h"' in src
    assert "osThreadDef" in src
    assert "osThreadCreate" in src
    # CMSIS-RTOS v1 kernel bring-up (v1 has no osKernelInitialize).
    assert "osKernelStart" in src
    assert "osKernelInitialize" not in src
    # The app task runs as the RTOS thread, not called directly from main.
    assert "app_led_blink_task(NULL);" not in src
    # HAL_InitTick re-run at lowest priority so ISRs can use FromISR APIs.
    assert "HAL_InitTick(" in src
    # configCHECK_FOR_STACK_OVERFLOW 2 requires the app-level hook.
    assert "vApplicationStackOverflowHook" in src


def test_render_main_c_rtos_chains_systick_for_hal_and_rtos_tick() -> None:
    """SysTick must serve both HAL tick and FreeRTOS tick: aliasing
    SysTick_Handler in FreeRTOSConfig.h would silently drop HAL_GetTick."""
    src = fps.render_main_c("led_blink", rtos=True)
    assert "void SysTick_Handler(void)" in src
    assert "HAL_IncTick();" in src
    assert "xPortSysTickHandler();" in src


def test_render_main_c_bare_metal_stays_bare() -> None:
    src = fps.render_main_c("led_blink", rtos=False)
    assert "cmsis_os" not in src
    assert "osThreadCreate" not in src
    assert "SysTick_Handler" not in src
    assert "app_led_blink_task((void const *)NULL);" in src


def test_render_freertos_config_h_has_required_macros() -> None:
    cfg = fps.render_freertos_config_h()
    normalized = " ".join(cfg.split())
    for macro in (
        "configUSE_PREEMPTION",
        "configCPU_CLOCK_HZ",
        "configTICK_RATE_HZ",
        "configMAX_PRIORITIES",
        "configMINIMAL_STACK_SIZE",
        "configTOTAL_HEAP_SIZE",
    ):
        assert macro in cfg, f"missing {macro}"
    # Port handler aliases (whitespace-normalized: the file aligns columns).
    assert "#define vPortSVCHandler SVC_Handler" in normalized
    assert "#define xPortPendSVHandler PendSV_Handler" in normalized
    # SysTick is chained in the generated main.c, never aliased here.
    assert "#define xPortSysTickHandler SysTick_Handler" not in normalized


def test_ensure_compilable_rtos_writes_freertos_config() -> None:
    project = copy_fixture("rtos")
    result = fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink", rtos=True)
    assert result["status"] == "ok"
    cfg = project / "Core" / "Inc" / "FreeRTOSConfig.h"
    assert cfg.exists()
    assert "configUSE_PREEMPTION" in cfg.read_text(encoding="utf-8")
    main_c = (project / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
    assert "osThreadCreate" in main_c
    assert any("FreeRTOSConfig.h" in action for action in result["actions"])


def test_ensure_compilable_bare_metal_does_not_write_freertos_config() -> None:
    project = copy_fixture("rtos-bare")
    fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink", rtos=False)
    assert not (project / "Core" / "Inc" / "FreeRTOSConfig.h").exists()


def test_ensure_compilable_preserves_existing_freertos_config() -> None:
    project = copy_fixture("rtos-existing")
    cfg = project / "Core" / "Inc" / "FreeRTOSConfig.h"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("#ifndef FREERTOS_CONFIG_H\n#define FREERTOS_CONFIG_H\n#endif\n", encoding="utf-8")
    fps.ensure_compilable(project, part="STM32F407VGTx", module="led_blink", rtos=True)
    assert "FREERTOS_CONFIG_H" in cfg.read_text(encoding="utf-8")
