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
