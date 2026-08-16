"""Tests for P2: LLM firmware codegen channel + failure-patch code overrides."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import llm_codegen  # noqa: E402

GOOD_HEADER = """#ifndef APP_SENSOR_READ_H
#define APP_SENSOR_READ_H

#include "main.h"
#include <stdint.h>

typedef enum
{
    APP_SENSOR_READ_OK = 0,
    APP_SENSOR_READ_NOT_READY,
    APP_SENSOR_READ_TIMEOUT,
    APP_SENSOR_READ_HAL_ERROR
} app_sensor_read_status_t;

void app_sensor_read_init(void);
void app_sensor_read_start(void);
void app_sensor_read_set(uint8_t enabled);
void app_sensor_read_task(void const *argument);

#endif
"""

GOOD_SOURCE = """#include "app_sensor_read.h"

static uint8_t app_sensor_read_enabled;

void app_sensor_read_init(void)
{
    app_sensor_read_enabled = 0U;
    __HAL_RCC_GPIOA_CLK_ENABLE();
}

void app_sensor_read_start(void)
{
    app_sensor_read_enabled = 1U;
}

void app_sensor_read_set(uint8_t enabled)
{
    app_sensor_read_enabled = enabled ? 1U : 0U;
}

void app_sensor_read_task(void const *argument)
{
    (void)argument;
    for (;;)
    {
        HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
        HAL_Delay(500U);
    }
}
"""


def _llm_payload(header: str = GOOD_HEADER, source: str = GOOD_SOURCE) -> str:
    return "Here is the module:\n" + json.dumps(
        {"module": "sensor_read", "header": header, "source": source, "notes": "assumes BMP280 on I2C1"}
    )


def test_extract_json_object_handles_c_code_braces() -> None:
    text = _llm_payload()
    parsed = llm_codegen.extract_json_object(text)
    assert parsed is not None
    assert parsed["module"] == "sensor_read"
    assert "HAL_GPIO_TogglePin" in parsed["source"]
    assert parsed["source"].count("{") == parsed["source"].count("}")


def test_extract_json_object_rejects_garbage() -> None:
    assert llm_codegen.extract_json_object("no json here") is None
    assert llm_codegen.extract_json_object("{broken json") is None


def test_validate_generated_pair_accepts_good_pair() -> None:
    problems = llm_codegen.validate_generated_pair("sensor_read", GOOD_HEADER, GOOD_SOURCE, rtos=False)
    assert problems == []


def test_validate_generated_pair_rejects_bad_output() -> None:
    problems = llm_codegen.validate_generated_pair("sensor_read", "#ifndef X\n", "int x;", rtos=False)
    assert any("required symbol" in p for p in problems)
    rtos_source = GOOD_SOURCE.replace('#include "app_sensor_read.h"', '#include "app_sensor_read.h"\n#include "cmsis_os.h"')
    problems = llm_codegen.validate_generated_pair("sensor_read", GOOD_HEADER, rtos_source, rtos=False)
    assert any("bare-metal" in p for p in problems)


def test_generate_app_module_not_enabled_by_default(tmp_path: Path) -> None:
    result = llm_codegen.generate_app_module(
        tmp_path, feature="sensor-read", pin="PA5", function="gpio-output",
        part="STM32F407VGTx", hal_handle="", rtos=False, goal="blink",
    )
    assert result["status"] == "not-enabled"


def test_generate_app_module_ok_constructs_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import llm_config
    monkeypatch.setenv("X_TEST_KEY", "placeholder-not-a-real-credential")
    config = llm_config.LLMConfig(provider="openai", api_key_env="X_TEST_KEY", codegen=True, max_tokens=8192)
    with patch("llm_config.load_config", return_value=config):
        with patch("llm_client.call_llm", return_value={"status": "ok", "text": _llm_payload()}):
            result = llm_codegen.generate_app_module(
                tmp_path, feature="sensor-read", pin="PA5", function="gpio-output",
                part="STM32F407VGTx", hal_handle="", rtos=False, goal="blink",
            )
    assert result["status"] == "ok"
    paths = [f["path"] for f in result["files"]]
    assert str(tmp_path / "Core" / "Inc" / "app_sensor_read.h") in paths
    assert str(tmp_path / "Core" / "Src" / "app_sensor_read.c") in paths


def test_generate_app_module_contract_violation_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import llm_config
    monkeypatch.setenv("X_TEST_KEY", "placeholder-not-a-real-credential")
    config = llm_config.LLMConfig(provider="openai", api_key_env="X_TEST_KEY", codegen=True)
    with patch("llm_config.load_config", return_value=config):
        with patch("llm_client.call_llm", return_value={"status": "ok", "text": _llm_payload(source="int x;")}):
            result = llm_codegen.generate_app_module(
                tmp_path, feature="sensor-read", pin="PA5", function="gpio-output",
                part="STM32F407VGTx", hal_handle="", rtos=False, goal="blink",
            )
    assert result["status"] == "error"
    assert "contract violations" in result["error"]


def test_workflow_firmware_plan_uses_llm_code_when_ok(tmp_path: Path) -> None:
    import workflow_runner as wr
    fixture = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
    scratch = REPO_ROOT / ".tmp-wf-tests" / tmp_path.name / "project"
    if scratch.exists():
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.parent.mkdir(parents=True, exist_ok=True)
    import shutil as _shutil
    _shutil.copytree(fixture, scratch)

    ctx = wr.WorkflowContext(feature="sensor-read", pin="PA5", function="gpio-output")
    state = wr.init_workflow(scratch, intent="develop-feature", goal="sensor read", context=ctx)
    state["stages"][0]["status"] = "completed"
    state["stages"][0]["evidence"] = {"parsed_requirements": {
        "feature": "sensor-read", "function": "gpio-output", "pin": "PA5", "instance": "", "part": "",
    }}
    state["stages"][1]["status"] = "completed"
    state["stages"][1]["evidence"] = {"selected_part": "STM32F407VGTx"}

    with patch("llm_codegen.generate_app_module", return_value={
        "status": "ok", "module": "sensor_read", "notes": "n",
        "files": [
            {"path": str(scratch / "Core" / "Inc" / "app_sensor_read.h"), "content": GOOD_HEADER},
            {"path": str(scratch / "Core" / "Src" / "app_sensor_read.c"), "content": GOOD_SOURCE},
        ],
    }):
        result = wr._stage_firmware_plan(scratch, ctx, state)

    assert result.status == "completed"
    assert result.evidence["llm_codegen"]["status"] == "ok"
    assert result.evidence["firmware_patch"]["generator"] == "llm"
    sources = {entry["path"]: entry["source"] for entry in result.evidence["firmware_patch"]["files_written"]}
    assert sources[str(scratch / "Core" / "Src" / "app_sensor_read.c")] == "llm"
    written = (scratch / "Core" / "Src" / "app_sensor_read.c").read_text(encoding="utf-8")
    assert "HAL_GPIO_TogglePin" in written


def test_workflow_applies_code_overrides_over_templates(tmp_path: Path) -> None:
    import workflow_runner as wr
    fixture = REPO_ROOT / "tests" / "fixtures" / "cubemx-basic"
    scratch = REPO_ROOT / ".tmp-wf-tests" / tmp_path.name / "project"
    if scratch.exists():
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.parent.mkdir(parents=True, exist_ok=True)
    import shutil as _shutil
    _shutil.copytree(fixture, scratch)

    ctx = wr.WorkflowContext(feature="led-blink", pin="PD12", function="gpio-output")
    state = wr.init_workflow(scratch, intent="develop-feature", goal="LED blink", context=ctx)
    state["stages"][0]["status"] = "completed"
    state["stages"][0]["evidence"] = {"parsed_requirements": {
        "feature": "led-blink", "function": "gpio-output", "pin": "PD12", "instance": "", "part": "",
    }}
    state["stages"][1]["status"] = "completed"
    state["stages"][1]["evidence"] = {"selected_part": "STM32F407VGTx"}
    patched_source = GOOD_SOURCE.replace("sensor_read", "led_blink")
    state["context"]["code_overrides"] = {"Core/Src/app_led_blink.c": patched_source}

    result = wr._stage_firmware_plan(scratch, ctx, state)
    assert result.status == "completed"
    written = (scratch / "Core" / "Src" / "app_led_blink.c").read_text(encoding="utf-8")
    assert "HAL_GPIO_TogglePin" in written  # from the override, not the template
    assert result.evidence["firmware_patch"]["code_overrides_applied"] == ["Core/Src/app_led_blink.c"]


def test_failure_analysis_accepts_only_app_file_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import llm_config
    import workflow_runner as wr
    monkeypatch.setenv("X_TEST_KEY", "placeholder-not-a-real-credential")
    config = llm_config.LLMConfig(provider="openai", api_key_env="X_TEST_KEY")
    response = {
        "status": "ok",
        "text": json.dumps({
            "root_cause": "compile error",
            "fix_action": "fix the source",
            "patch_fields": {},
            "patch_files": {
                "Core/Src/app_led_blink.c": patched_minimal_source(),
                "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c": "/* malicious */",
                "Core/Src/main.c": "int main(void){}",
                "../escape.c": "x",
            },
        }),
    }
    state = {"workflow_id": "wf-test", "goal": "g", "context": {}, "stages": []}
    failed = {"id": "build", "attempts": 1, "error": "compile failed", "evidence": {}}
    with patch("llm_config.load_config", return_value=config):
        with patch("llm_client.call_llm", return_value=response):
            analysis = wr._llm_analyze_failure_and_patch(tmp_path, state, failed)

    assert analysis["status"] == "ok"
    assert analysis["code_overrides_accepted"] == ["Core/Src/app_led_blink.c"]
    assert len(analysis["code_overrides_rejected"]) == 3
    assert set(state["context"]["code_overrides"]) == {"Core/Src/app_led_blink.c"}


def patched_minimal_source() -> str:
    body = GOOD_SOURCE.replace("sensor_read", "led_blink")
    return body
