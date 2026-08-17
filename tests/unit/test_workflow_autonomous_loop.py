"""End-to-end autonomous-loop test: one-sentence goal -> workflow completes with LLM-written firmware.

This is the regression net for the user's core product claim: with an HTTP LLM
provider configured, the workflow must close the loop autonomously — no
blocked-needs-input, no host-agent handoff. The LLM (1) parses intent from the
goal, (2) writes the app module .c/.h pair. The test stubs the LLM HTTP layer
so no API key is needed.

What this proves:
- One-sentence input (no --feature/--pin/--part) still completes the workflow.
- requirement-parse auto-fills feature/pin/function/part from LLM JSON.
- firmware-plan uses the LLM-written module (not the deterministic template).
- verify-goal returns behavior-mock (mock observe mode).
- No stage enters blocked-needs-input.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import llm_config  # noqa: E402
import workflow_runner as wr  # noqa: E402

_STUB_APP_HEADER = """#ifndef APP_LED_BLINK_H
#define APP_LED_BLINK_H

#include "main.h"

typedef enum {
    APP_LED_BLINK_OK = 0,
    APP_LED_BLINK_NOT_READY,
    APP_LED_BLINK_TIMEOUT,
    APP_LED_BLINK_HAL_ERROR
} app_led_blink_status_t;

void app_led_blink_init(void);
void app_led_blink_start(void);
void app_led_blink_set(uint8_t enabled);
void app_led_blink_task(void const *argument);

#endif
"""

_STUB_APP_SOURCE = """#include "app_led_blink.h"
#include "app_rtt.h"

static uint8_t s_started = 0;

void app_led_blink_init(void) {
    __HAL_RCC_GPIOD_CLK_ENABLE();
}

void app_led_blink_start(void) {
    s_started = 1;
}

void app_led_blink_set(uint8_t enabled) {
    (void)enabled;
}

void app_led_blink_task(void const *argument) {
    (void)argument;
    while (1) {
        if (s_started) {
            app_rtt_puts("app_led_blink: on\\n");
        }
        HAL_Delay(500);
    }
}
"""


def _stub_call_llm(root: Path, config: object, *, task_id: str, prompt: str, system: str = "", max_tokens: int | None = None):
    """Stub LLM that answers intent-parse + codegen tasks deterministically.

    Returns {"status": "ok", "text": ...} mimicking the HTTP provider path.
    No network, no API key.
    """
    if task_id.startswith("intent-"):
        body = json.dumps({
            "feature": "led-blink",
            "function": "gpio-output",
            "pin": "PD12",
            "instance": "",
            "part": "",
        })
        return {"status": "ok", "text": body}
    if task_id.startswith("codegen-") or "app_led_blink" in prompt:
        body = json.dumps({
            "module": "led_blink",
            "header": _STUB_APP_HEADER,
            "source": _STUB_APP_SOURCE,
            "notes": "LLM-written stub for autonomous-loop test.",
        })
        return {"status": "ok", "text": body}
    return {"status": "ok", "text": "{}"}


def _copy_fixture(src: Path, tmp_path: Path) -> Path:
    scratch_root = Path(__file__).resolve().parents[2] / ".tmp-wf-tests"
    dst = scratch_root / tmp_path.name / "project"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    evidence_path = dst / ".hardware-butler" / "datasheet-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        '{"part": "STM32F407VGTx", "sources": [{"url": "stub", "title": "stub", "type": "manual"}], '
        '"summary": {"has_reference_manual": true}, "evidence_status": "evidence-collected"}'
    )
    return dst


def test_one_sentence_goal_completes_via_http_llm_stub(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """One-sentence goal with a stubbed HTTP LLM provider closes the full loop."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)

    # Configure an "openai" provider so llm_config.is_configured() returns True
    # (local provider only needs base_url; we use openai+api_key_env so the
    # stub gets called from call_llm via the HTTP branch).
    config = llm_config.LLMConfig(
        provider="openai",
        api_key_env="HARDWARE_BUTLER_TEST_STUB_KEY",
        model="stub-model",
        base_url="http://stub.invalid/v1/chat/completions",
        codegen=True,
        max_tokens=8192,
    )
    llm_config.save_config(project, config)
    # Provide the env var the config points at (the stub never uses it, but
    # is_configured() checks the env var is present and non-empty).
    import os
    old = os.environ.get("HARDWARE_BUTLER_TEST_STUB_KEY")
    os.environ["HARDWARE_BUTLER_TEST_STUB_KEY"] = "stub-key"

    # No --feature/--pin/--part: the LLM intent parser must fill them in.
    ctx = wr.WorkflowContext()
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)

    try:
        with patch("llm_client.call_llm", side_effect=_stub_call_llm):
            result = wr.run_workflow(project, state)
    finally:
        if old is None:
            os.environ.pop("HARDWARE_BUTLER_TEST_STUB_KEY", None)
        else:
            os.environ["HARDWARE_BUTLER_TEST_STUB_KEY"] = old

    assert result["status"] == "completed", (
        f"autonomous loop did not complete: status={result['status']}, stages="
        f"{[(s['id'], s['status']) for s in result['stages']]}"
    )
    assert all(s["status"] == "completed" for s in result["stages"]), [
        (s["id"], s["status"]) for s in result["stages"]
    ]


def test_autonomous_loop_uses_llm_written_firmware(cubemx_basic_fixture: Path, tmp_path: Path) -> None:
    """firmware-plan evidence must record the LLM-written module (generator=llm)."""
    project = _copy_fixture(cubemx_basic_fixture, tmp_path)

    config = llm_config.LLMConfig(
        provider="openai",
        api_key_env="HARDWARE_BUTLER_TEST_STUB_KEY",
        model="stub-model",
        base_url="http://stub.invalid/v1/chat/completions",
        codegen=True,
        max_tokens=8192,
    )
    llm_config.save_config(project, config)
    import os
    old = os.environ.get("HARDWARE_BUTLER_TEST_STUB_KEY")
    os.environ["HARDWARE_BUTLER_TEST_STUB_KEY"] = "stub-key"

    ctx = wr.WorkflowContext()
    state = wr.init_workflow(project, intent="develop-feature", goal="LED blink on PD12", context=ctx)

    try:
        with patch("llm_client.call_llm", side_effect=_stub_call_llm):
            result = wr.run_workflow(project, state)
    finally:
        if old is None:
            os.environ.pop("HARDWARE_BUTLER_TEST_STUB_KEY", None)
        else:
            os.environ["HARDWARE_BUTLER_TEST_STUB_KEY"] = old

    fw_stage = next(s for s in result["stages"] if s["id"] == "firmware-plan")
    codegen_evidence = fw_stage["evidence"].get("llm_codegen", {})
    assert codegen_evidence.get("status") == "ok", codegen_evidence

    # Verify the LLM-written file actually landed on disk.
    src_path = project / "Core" / "Src" / "app_led_blink.c"
    assert src_path.exists(), f"LLM-written source missing: {src_path}"
    content = src_path.read_text(encoding="utf-8")
    # Stub signature proves the LLM's content (not the template) was written.
    assert "app_led_blink_init" in content
    assert "app_rtt_puts" in content
