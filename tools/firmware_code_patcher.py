"""Generate safe app-layer firmware modules from a firmware intent plan.

The patcher never edits CubeMX generated driver files. It writes only explicit
application files under `Core/Inc`, `Core/Src`, and an integration note under
`docs/firmware-patches` after `--write --confirm-write`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firmware_intent_planner  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402

USER_CODE_BLOCK_RE = re.compile(
    r"(?P<begin>/\*\s*USER CODE BEGIN (?P<name>[^*]+?)\s*\*/)(?P<body>.*?)(?P<end>/\*\s*USER CODE END (?P=name)\s*\*/)",
    re.DOTALL,
)


def module_name(feature: str) -> str:
    name = firmware_intent_planner.normalize_feature(feature).replace("-", "_")
    return re.sub(r"[^a-z0-9_]+", "_", name) or "feature"


def gpio_symbols(pin: str) -> tuple[str, str]:
    match = re.fullmatch(r"P([A-K])(\d{1,2})", pin.strip().upper())
    if not match:
        return "GPIOx", "GPIO_PIN_x"
    port, number = match.groups()
    return f"GPIO{port}", f"GPIO_PIN_{int(number)}"


def gpio_clock_enable(port: str) -> str:
    """RCC AHB1 enable macro line for a GPIO port; empty for unknown ports."""
    match = re.fullmatch(r"GPIO([A-K])", port.strip().upper())
    if not match:
        return ""
    return f"    __HAL_RCC_GPIO{match.group(1)}_CLK_ENABLE();"


def preview_patch(root: Path, *, feature: str, pin: str = "", function: str = "", rtos: bool = True) -> dict[str, Any]:
    root = root.resolve()
    plan = firmware_intent_planner.plan_implementation(root, feature=feature, pin=pin, function=function, rtos=rtos)
    module = module_name(feature)
    files = generated_files(root, plan, module, pin=pin)
    return {
        "schema_version": 1,
        "status": "preview",
        "root": str(root),
        "feature": feature,
        "module": module,
        "intent_plan": plan,
        "write_policy": {
            "default": "preview only",
            "requires": ["--write", "--confirm-write"],
            "allowed_paths": ["Core/Inc/app_*.h", "Core/Src/app_*.c", "docs/firmware-patches/*.md"],
            "forbidden_paths": plan["cube_generated_boundaries"]["forbidden_by_default"],
        },
        "files": [{"path": str(path), "content": content} for path, content in files.items()],
    }


def preview_integration_patch(root: Path, *, feature: str, pin: str = "", function: str = "", rtos: bool = True) -> dict[str, Any]:
    root = root.resolve()
    app_preview = preview_patch(root, feature=feature, pin=pin, function=function, rtos=rtos)
    module = app_preview["module"]
    plan = app_preview["intent_plan"]
    missing_app = missing_app_files(root, module)
    if missing_app:
        targets: list[dict[str, Any]] = []
        status = "blocked-missing-app-module"
        warnings: list[dict[str, Any]] = []
    else:
        targets = integration_targets(root, module, plan)
        blocking = [item for item in targets if item["status"] == "blocked"]
        warnings = [item for item in targets if item["status"] == "warning"]
        status = "blocked-missing-user-code-block" if blocking else ("ready-with-warnings" if warnings else "ready-to-write")
    blocking = [item for item in targets if item["status"] == "blocked"]
    proposed = proposed_integration_changes(targets)
    return {
        "schema_version": 1,
        "status": status,
        "dry_run": True,
        "root": str(root),
        "feature": feature,
        "module": module,
        "intent_plan": plan,
        "target_files": [item["path"] for item in targets],
        "proposed_changes": proposed,
        "diff_preview": "\n".join(item["diff_preview"] for item in targets if item.get("diff_preview")),
        "missing_app_files": [str(path) for path in missing_app],
        "write_policy": {
            "default": "preview only",
            "requires": ["--write", "--confirm-write"],
            "allowed_paths": ["Core/Src/main.c", "Core/Src/freertos.c"],
            "only_user_code_blocks": True,
        },
        "targets": targets,
        "write_required_confirmation": ["--write", "--confirm-write"],
        "written": False,
        "next_actions": integration_next_actions(status, warnings),
    }


def missing_app_files(root: Path, module: str) -> list[Path]:
    required = [
        root / "Core" / "Inc" / f"app_{module}.h",
        root / "Core" / "Src" / f"app_{module}.c",
    ]
    return [path for path in required if not path.exists()]


def proposed_integration_changes(targets: list[dict[str, Any]]) -> list[dict[str, str]]:
    changes = []
    for target in targets:
        if target.get("status") not in {"ready-to-write", "warning"}:
            continue
        for item in target.get("insertions", []):
            changes.append(
                {
                    "file": target.get("path", ""),
                    "block": item.get("block", ""),
                    "insert": item.get("code", ""),
                    "reason": item.get("reason", ""),
                    "target_status": target.get("status", ""),
                }
            )
    return changes


def integration_targets(root: Path, module: str, plan: dict[str, Any]) -> list[dict[str, Any]]:
    main_path = root / "Core" / "Src" / "main.c"
    if not main_path.exists():
        return [
            {
                "path": str(main_path),
                "status": "blocked",
                "reason": "Core/Src/main.c is missing.",
                "diff_preview": "",
                "insertions": [],
            }
        ]
    main_original = main_path.read_text(encoding="utf-8", errors="replace")
    insertions = [
        user_code_insertion("Includes", f'#include "app_{module}.h"', "Include generated app module API."),
        user_code_insertion("2", f"app_{module}_init();", "Initialize app module after CubeMX peripheral init."),
        user_code_insertion("2", f"app_{module}_start();", "Start the app module from an explicit safe startup hook."),
    ]
    main_target = apply_user_code_insertions(main_original, insertions)
    targets = [
        target_result(main_path, main_original, main_target, insertions, required=True),
    ]
    if plan["freertos"].get("enabled"):
        rtos_target = find_rtos_user_code_file(root)
        rtos_block = rtos_target[1] if rtos_target else "RTOS_THREADS"
        rtos_insertions = [
            user_code_insertion(
                rtos_block,
                f"osThreadDef(app_{module}, app_{module}_task, osPriorityNormal, 0, 256);\nosThreadCreate(osThread(app_{module}), NULL);",
                "Create a conservative CMSIS-RTOS task for the app module.",
            )
        ]
        if rtos_target:
            rtos_path = rtos_target[0]
            original = rtos_path.read_text(encoding="utf-8", errors="replace")
            updated = apply_user_code_insertions(original, rtos_insertions)
            targets.append(target_result(rtos_path, original, updated, rtos_insertions, required=False))
        else:
            targets.append(
                {
                    "path": str(root / "Core" / "Src" / "freertos.c"),
                    "status": "warning",
                    "reason": "No USER CODE BEGIN RTOS_THREADS block found; task creation remains manual.",
                    "diff_preview": "",
                    "insertions": rtos_insertions,
                }
            )
    return targets


def user_code_insertion(block: str, code: str, reason: str) -> dict[str, str]:
    return {"block": block, "code": code, "reason": reason}


def apply_user_code_insertions(text: str, insertions: list[dict[str, str]]) -> str:
    updated = text
    for item in insertions:
        block = item["block"]
        code = item["code"].rstrip()
        updated = insert_into_user_code_block(updated, block, code)
    return updated


def insert_into_user_code_block(text: str, block: str, code: str) -> str:
    pattern = re.compile(
        rf"(?P<begin>/\*\s*USER CODE BEGIN {re.escape(block)}\s*\*/)(?P<body>.*?)(?P<end>/\*\s*USER CODE END {re.escape(block)}\s*\*/)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return text
    body = match.group("body")
    if code_already_present(body, code):
        return text
    insertion = "\n" + indent_for_block(block, code) + "\n"
    return text[: match.start("body")] + body.rstrip() + insertion + text[match.start("end") :]


def code_already_present(body: str, code: str) -> bool:
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    code_lines = [line.strip() for line in code.splitlines() if line.strip()]
    if not code_lines:
        return True
    for index in range(0, len(body_lines) - len(code_lines) + 1):
        if body_lines[index : index + len(code_lines)] == code_lines:
            return True
    return False


def indent_for_block(block: str, code: str) -> str:
    if block in {"2", "3", "RTOS_THREADS"}:
        return "\n".join(f"  {line}" if line else line for line in code.splitlines())
    return code


def target_result(path: Path, original: str, updated: str, insertions: list[dict[str, str]], *, required: bool) -> dict[str, Any]:
    missing = [item["block"] for item in insertions if not user_code_block_exists(original, item["block"])]
    changed = original != updated
    if missing and required:
        status = "blocked"
        reason = f"Missing required USER CODE block(s): {', '.join(missing)}."
    elif missing:
        status = "warning"
        reason = f"Missing optional USER CODE block(s): {', '.join(missing)}."
    else:
        status = "ready-to-write"
        reason = "All requested insertions are inside CubeMX USER CODE blocks." if changed else "Insertions already present."
    return {
        "path": str(path),
        "status": status,
        "reason": reason,
        "diff_preview": unified_diff(original, updated, fromfile=str(path), tofile=f"{path} (integrated)"),
        "insertions": insertions,
        "changed": changed,
        "missing_blocks": missing,
    }


def user_code_block_exists(text: str, block: str) -> bool:
    return bool(
        re.search(
            rf"/\*\s*USER CODE BEGIN {re.escape(block)}\s*\*/.*?/\*\s*USER CODE END {re.escape(block)}\s*\*/",
            text,
            flags=re.DOTALL,
        )
    )


def find_rtos_user_code_file(root: Path) -> tuple[Path, str] | None:
    for rel in ("Core/Src/freertos.c", "Core/Src/main.c"):
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if user_code_block_exists(text, "RTOS_THREADS"):
            return path, "RTOS_THREADS"
        if user_code_block_exists(text, "5"):
            return path, "5"
    return None


def unified_diff(original: str, updated: str, *, fromfile: str, tofile: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )


def integration_next_actions(status: str, warnings: list[dict[str, Any]]) -> list[str]:
    if status == "blocked-missing-app-module":
        return ["Run firmware-patch --write --confirm-write for this feature before adding USER CODE integration hooks."]
    if status == "blocked-missing-user-code-block":
        return ["Open or regenerate the project with CubeMX so USER CODE blocks are present, then retry firmware-integrate."]
    actions = ["Review diff_preview, write only with --write --confirm-write, then run a build before any flash/debug action."]
    if warnings:
        actions.append("Resolve warnings manually, especially FreeRTOS task creation if RTOS thread hooks are missing.")
    return actions


def write_integration_patch(preview: dict[str, Any], *, confirm_write: bool) -> dict[str, Any]:
    if str(preview.get("status", "")).startswith("blocked-"):
        raise ValueError("integration patch is blocked because required USER CODE blocks are missing")
    if not confirm_write:
        raise ValueError("firmware integration writing requires --confirm-write")
    validate_integration_current_state(preview)
    written = []
    for target in preview.get("targets", []):
        if target.get("status") not in {"ready-to-write"} or not target.get("changed"):
            continue
        path = Path(target["path"])
        original = path.read_text(encoding="utf-8", errors="replace")
        updated = apply_user_code_insertions(original, target.get("insertions", []))
        written.append(
            safe_io.safe_write_text(
                path,
                updated,
                allowed_roots=runtime_context.allowed_write_roots(Path(preview["root"])),
                backup_existing=True,
            )
        )
    result = dict(preview)
    result["status"] = "written"
    result["written"] = written
    return result


def validate_integration_current_state(preview: dict[str, Any]) -> None:
    root = Path(str(preview.get("root") or ".")).resolve()
    module = str(preview.get("module") or "")
    missing_app = missing_app_files(root, module)
    if missing_app:
        raise ValueError(f"app module changed since preview; missing files: {[str(path) for path in missing_app]}")
    for target in preview.get("targets", []):
        if target.get("status") not in {"ready-to-write"} or not target.get("changed"):
            continue
        path = Path(str(target.get("path") or ""))
        safe_io.validate_write_path(path, allowed_roots=runtime_context.allowed_write_roots(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [item.get("block", "") for item in target.get("insertions", []) if not user_code_block_exists(text, str(item.get("block", "")))]
        if missing:
            raise ValueError(f"USER CODE block(s) changed since preview in {path}: {', '.join(missing)}")


def generated_files(root: Path, plan: dict[str, Any], module: str, *, pin: str) -> dict[Path, str]:
    header = root / "Core" / "Inc" / f"app_{module}.h"
    source = root / "Core" / "Src" / f"app_{module}.c"
    note = root / "docs" / "firmware-patches" / f"app_{module}.md"
    return {
        header: render_header(module, plan),
        source: render_source(module, plan, pin=pin),
        note: render_integration_note(module, plan),
    }


def render_header(module: str, plan: dict[str, Any]) -> str:
    guard = f"APP_{module.upper()}_H"
    return f"""#ifndef {guard}
#define {guard}

#include "main.h"
#include <stdint.h>

typedef enum
{{
    APP_{module.upper()}_OK = 0,
    APP_{module.upper()}_NOT_READY,
    APP_{module.upper()}_TIMEOUT,
    APP_{module.upper()}_HAL_ERROR
}} app_{module}_status_t;

void app_{module}_init(void);
void app_{module}_start(void);
void app_{module}_set(uint8_t enabled);
void app_{module}_task(void const *argument);

#endif
"""


def render_source(module: str, plan: dict[str, Any], *, pin: str) -> str:
    function = plan["requested_function"]
    if function == "gpio-output":
        port, gpio_pin = gpio_symbols(pin)
        return render_gpio_source(module, port, gpio_pin, plan)
    if function == "i2c":
        return render_i2c_source(module, plan)
    if function == "spi":
        return render_spi_source(module, plan)
    if function == "uart":
        return render_uart_source(module, plan)
    if function == "adc":
        return render_adc_source(module, plan)
    if function == "pwm":
        return render_pwm_source(module, plan)
    if function == "can":
        return render_can_source(module, plan)
    return render_generic_source(module, plan)


def render_gpio_source(module: str, port: str, gpio_pin: str, plan: dict[str, Any]) -> str:
    delay_fn = "osDelay" if plan["freertos"].get("enabled") else "HAL_Delay"
    include_rtos = '#include "cmsis_os.h"\n' if plan["freertos"].get("enabled") else ""
    clock_enable = gpio_clock_enable(port)
    return f"""#include "app_{module}.h"
{include_rtos}
static uint8_t app_{module}_enabled;

void app_{module}_init(void)
{{
    app_{module}_enabled = 0U;
{clock_enable}
    HAL_GPIO_WritePin({port}, {gpio_pin}, GPIO_PIN_RESET);
}}

void app_{module}_start(void)
{{
    app_{module}_enabled = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_enabled = enabled ? 1U : 0U;
    HAL_GPIO_WritePin({port}, {gpio_pin}, app_{module}_enabled ? GPIO_PIN_SET : GPIO_PIN_RESET);
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        app_{module}_set(1U);
        {delay_fn}(500U);
        app_{module}_set(0U);
        {delay_fn}(500U);
    }}
}}
"""


def rtos_include(plan: dict[str, Any]) -> str:
    return '#include "cmsis_os.h"\n' if plan["freertos"].get("enabled") else ""


def rtos_delay(plan: dict[str, Any], ms: int) -> str:
    fn = "osDelay" if plan["freertos"].get("enabled") else "HAL_Delay"
    return f"{fn}({ms}U);"


def rtos_mutex_members(module: str, plan: dict[str, Any]) -> str:
    if not plan["freertos"].get("enabled"):
        return ""
    return f"""static osMutexId app_{module}_mutex;
osMutexDef(app_{module}_mutex);
"""


def rtos_mutex_init(module: str, plan: dict[str, Any]) -> str:
    if not plan["freertos"].get("enabled"):
        return ""
    return f"    app_{module}_mutex = osMutexCreate(osMutex(app_{module}_mutex));\n"


def rtos_mutex_lock(module: str, plan: dict[str, Any]) -> str:
    if not plan["freertos"].get("enabled"):
        return ""
    return f"""    if (osMutexWait(app_{module}_mutex, APP_{module.upper()}_TIMEOUT_MS) != osOK)
    {{
        return APP_{module.upper()}_TIMEOUT;
    }}
"""


def rtos_mutex_unlock(module: str, plan: dict[str, Any]) -> str:
    if not plan["freertos"].get("enabled"):
        return ""
    return f"    (void)osMutexRelease(app_{module}_mutex);\n"


def app_handle(plan: dict[str, Any], fallback: str) -> str:
    return plan["hal"].get("handle") or fallback


def render_i2c_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "hi2c1")
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_TIMEOUT_MS 100U

extern I2C_HandleTypeDef {handle};
{rtos_mutex_members(module, plan)}static uint8_t app_{module}_started;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
{rtos_mutex_init(module, plan)}    app_{module}_started = 0U;
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    app_{module}_started = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

app_{module}_status_t app_{module}_write_read(uint16_t device_address, const uint8_t *tx_data, uint16_t tx_size, uint8_t *rx_data, uint16_t rx_size)
{{
    HAL_StatusTypeDef hal_status;
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
{rtos_mutex_lock(module, plan)}    hal_status = HAL_I2C_Master_Transmit(&{handle}, device_address, (uint8_t *)tx_data, tx_size, APP_{module.upper()}_TIMEOUT_MS);
    if (hal_status == HAL_OK && rx_data != 0 && rx_size > 0U)
    {{
        hal_status = HAL_I2C_Master_Receive(&{handle}, device_address, rx_data, rx_size, APP_{module.upper()}_TIMEOUT_MS);
    }}
{rtos_mutex_unlock(module, plan)}    app_{module}_last_status = (hal_status == HAL_OK) ? APP_{module.upper()}_OK : APP_{module.upper()}_HAL_ERROR;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        {rtos_delay(plan, 100)}
    }}
}}
"""


def render_spi_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "hspi1")
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_TIMEOUT_MS 100U

extern SPI_HandleTypeDef {handle};
{rtos_mutex_members(module, plan)}static uint8_t app_{module}_started;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
{rtos_mutex_init(module, plan)}    app_{module}_started = 0U;
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    app_{module}_started = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

app_{module}_status_t app_{module}_transfer(const uint8_t *tx_data, uint8_t *rx_data, uint16_t size)
{{
    HAL_StatusTypeDef hal_status;
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
{rtos_mutex_lock(module, plan)}    hal_status = HAL_SPI_TransmitReceive(&{handle}, (uint8_t *)tx_data, rx_data, size, APP_{module.upper()}_TIMEOUT_MS);
{rtos_mutex_unlock(module, plan)}    app_{module}_last_status = (hal_status == HAL_OK) ? APP_{module.upper()}_OK : APP_{module.upper()}_HAL_ERROR;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        {rtos_delay(plan, 100)}
    }}
}}
"""


def render_uart_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "huart2")
    queue_members = ""
    queue_init = ""
    queue_put = ""
    if plan["freertos"].get("enabled"):
        queue_members = f"""static osMessageQId app_{module}_rx_queue;
osMessageQDef(app_{module}_rx_queue, 32, uint8_t);
"""
        queue_init = f"    app_{module}_rx_queue = osMessageCreate(osMessageQ(app_{module}_rx_queue), 0);\n"
        queue_put = f"            (void)osMessagePut(app_{module}_rx_queue, rx_byte, 0U);\n"
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_TIMEOUT_MS 20U

extern UART_HandleTypeDef {handle};
{queue_members}static uint8_t app_{module}_started;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
{queue_init}    app_{module}_started = 0U;
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    app_{module}_started = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

app_{module}_status_t app_{module}_write(const uint8_t *data, uint16_t size)
{{
    HAL_StatusTypeDef hal_status;
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
    hal_status = HAL_UART_Transmit(&{handle}, (uint8_t *)data, size, APP_{module.upper()}_TIMEOUT_MS);
    app_{module}_last_status = (hal_status == HAL_OK) ? APP_{module.upper()}_OK : APP_{module.upper()}_HAL_ERROR;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    uint8_t rx_byte = 0U;
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        if (HAL_UART_Receive(&{handle}, &rx_byte, 1U, APP_{module.upper()}_TIMEOUT_MS) == HAL_OK)
        {{
{queue_put}            app_{module}_last_status = APP_{module.upper()}_OK;
        }}
        else
        {{
            {rtos_delay(plan, 5)}
        }}
    }}
}}
"""


def render_adc_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "hadc1")
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_TIMEOUT_MS 20U

extern ADC_HandleTypeDef {handle};
static uint8_t app_{module}_started;
static uint32_t app_{module}_last_sample;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
    app_{module}_started = 0U;
    app_{module}_last_sample = 0U;
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    app_{module}_started = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

app_{module}_status_t app_{module}_sample(uint32_t *sample)
{{
    HAL_StatusTypeDef hal_status;
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
    hal_status = HAL_ADC_Start(&{handle});
    if (hal_status == HAL_OK)
    {{
        hal_status = HAL_ADC_PollForConversion(&{handle}, APP_{module.upper()}_TIMEOUT_MS);
    }}
    if (hal_status == HAL_OK)
    {{
        app_{module}_last_sample = HAL_ADC_GetValue(&{handle});
        if (sample != 0)
        {{
            *sample = app_{module}_last_sample;
        }}
    }}
    (void)HAL_ADC_Stop(&{handle});
    app_{module}_last_status = (hal_status == HAL_OK) ? APP_{module.upper()}_OK : APP_{module.upper()}_HAL_ERROR;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        (void)app_{module}_sample(0);
        {rtos_delay(plan, 100)}
    }}
}}
"""


def render_pwm_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "htim1")
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_CHANNEL TIM_CHANNEL_1

extern TIM_HandleTypeDef {handle};
static uint8_t app_{module}_started;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
    app_{module}_started = 0U;
    __HAL_TIM_SET_COMPARE(&{handle}, APP_{module.upper()}_CHANNEL, 0U);
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    if (HAL_TIM_PWM_Start(&{handle}, APP_{module.upper()}_CHANNEL) == HAL_OK)
    {{
        app_{module}_started = 1U;
        app_{module}_last_status = APP_{module.upper()}_OK;
    }}
    else
    {{
        app_{module}_last_status = APP_{module.upper()}_HAL_ERROR;
    }}
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
    if (!app_{module}_started)
    {{
        __HAL_TIM_SET_COMPARE(&{handle}, APP_{module.upper()}_CHANNEL, 0U);
    }}
}}

app_{module}_status_t app_{module}_set_duty(uint32_t compare_value)
{{
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
    __HAL_TIM_SET_COMPARE(&{handle}, APP_{module.upper()}_CHANNEL, compare_value);
    app_{module}_last_status = APP_{module.upper()}_OK;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        {rtos_delay(plan, 100)}
    }}
}}
"""


def render_can_source(module: str, plan: dict[str, Any]) -> str:
    handle = app_handle(plan, "hcan1")
    return f"""#include "app_{module}.h"
{rtos_include(plan)}
#define APP_{module.upper()}_TIMEOUT_MS 10U

extern CAN_HandleTypeDef {handle};
static uint8_t app_{module}_started;
static app_{module}_status_t app_{module}_last_status = APP_{module.upper()}_NOT_READY;

void app_{module}_init(void)
{{
    app_{module}_started = 0U;
    app_{module}_last_status = APP_{module.upper()}_NOT_READY;
}}

void app_{module}_start(void)
{{
    if (HAL_CAN_Start(&{handle}) == HAL_OK)
    {{
        app_{module}_started = 1U;
        app_{module}_last_status = APP_{module.upper()}_OK;
    }}
    else
    {{
        app_{module}_last_status = APP_{module.upper()}_HAL_ERROR;
    }}
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

app_{module}_status_t app_{module}_send(uint32_t std_id, const uint8_t *data, uint8_t dlc)
{{
    CAN_TxHeaderTypeDef header;
    uint32_t mailbox = 0U;
    if (!app_{module}_started)
    {{
        return APP_{module.upper()}_NOT_READY;
    }}
    header.StdId = std_id;
    header.ExtId = 0U;
    header.IDE = CAN_ID_STD;
    header.RTR = CAN_RTR_DATA;
    header.DLC = dlc;
    header.TransmitGlobalTime = DISABLE;
    app_{module}_last_status = (HAL_CAN_AddTxMessage(&{handle}, &header, (uint8_t *)data, &mailbox) == HAL_OK) ? APP_{module.upper()}_OK : APP_{module.upper()}_HAL_ERROR;
    return app_{module}_last_status;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        {rtos_delay(plan, 100)}
    }}
}}
"""


def render_generic_source(module: str, plan: dict[str, Any]) -> str:
    handle = plan["hal"].get("handle") or ""
    extern_handle = f"extern {hal_handle_type(handle)} {handle};\n" if handle else ""
    return f"""#include "app_{module}.h"

{extern_handle}static uint8_t app_{module}_started;

void app_{module}_init(void)
{{
    app_{module}_started = 0U;
}}

void app_{module}_start(void)
{{
    app_{module}_started = 1U;
}}

void app_{module}_set(uint8_t enabled)
{{
    app_{module}_started = enabled ? 1U : 0U;
}}

void app_{module}_task(void const *argument)
{{
    (void)argument;
    app_{module}_init();
    app_{module}_start();
    for (;;)
    {{
        HAL_Delay(100U);
    }}
}}
"""


def hal_handle_type(handle: str) -> str:
    if handle.startswith("hi2c"):
        return "I2C_HandleTypeDef"
    if handle.startswith("hspi"):
        return "SPI_HandleTypeDef"
    if handle.startswith("huart"):
        return "UART_HandleTypeDef"
    if handle.startswith("htim"):
        return "TIM_HandleTypeDef"
    if handle.startswith("hadc"):
        return "ADC_HandleTypeDef"
    if handle.startswith("hcan"):
        return "CAN_HandleTypeDef"
    return "void *"


def render_integration_note(module: str, plan: dict[str, Any]) -> str:
    lines = [
        "# Firmware Patch Integration",
        "",
        f"- Feature: {plan['feature']}",
        f"- Function: `{plan['requested_function']}`",
        f"- IOC: `{plan['ioc_file']}`",
        f"- RTOS requested: {plan['rtos_requested']}",
        f"- RTOS available: {plan['rtos_available']}",
        "",
        "## Files",
        "",
        f"- `Core/Inc/app_{module}.h`",
        f"- `Core/Src/app_{module}.c`",
        "",
        "## CubeMX Integration",
        "",
        f"- Add `#include \"app_{module}.h\"` inside a CubeMX `USER CODE BEGIN Includes` block.",
        f"- Call `app_{module}_init()` inside a CubeMX init user-code block after GPIO/peripheral init.",
        f"- If FreeRTOS is enabled, create a task that calls `app_{module}_task` with a conservative priority and stack.",
        f"- HAL handle: `{plan['hal'].get('handle') or 'needs verification'}`",
        f"- Timeout: {plan.get('timeout_ms', 0)} ms for blocking HAL calls where applicable.",
        "",
        "## Required Hooks",
        "",
    ]
    for item in plan.get("integration_hooks", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Error And Recovery Policy",
            "",
            f"- Return contract: {plan.get('error_policy', {}).get('return_contract', 'status enum')}",
        ]
    )
    for item in plan.get("recovery_policy", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
        "## Safety",
        "",
        ]
    )
    for item in plan["safe_defaults"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Verification", ""])
    for item in plan["verification"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_patch(preview: dict[str, Any], *, confirm_write: bool) -> dict[str, Any]:
    if not confirm_write:
        raise ValueError("firmware patch writing requires --confirm-write")
    written = []
    for item in preview["files"]:
        path = Path(item["path"])
        written.append(
            safe_io.safe_write_text(
                path,
                item["content"],
                allowed_roots=runtime_context.allowed_write_roots(Path(preview["root"])),
                backup_existing=True,
            )
        )
    result = dict(preview)
    result["status"] = "written"
    result["written"] = written
    result.pop("files", None)
    return result


def render_markdown(preview: dict[str, Any]) -> str:
    lines = [
        "# Firmware Patch Preview",
        "",
        f"- Root: `{preview['root']}`",
        f"- Feature: {preview['feature']}",
        f"- Module: `app_{preview['module']}`",
        f"- Status: `{preview['status']}`",
        "",
        "## Files",
        "",
    ]
    for item in preview.get("files", []):
        lines.append(f"- `{item['path']}`")
    if preview.get("written"):
        lines.extend(["", "## Written", ""])
        for item in preview["written"]:
            lines.append(f"- `{item}`")
    lines.extend(["", "## Policy", ""])
    for item in preview["write_policy"]["allowed_paths"]:
        lines.append(f"- allowed: `{item}`")
    for item in preview["write_policy"]["forbidden_paths"]:
        lines.append(f"- forbidden: `{item}`")
    return "\n".join(lines) + "\n"


def render_integration_markdown(preview: dict[str, Any]) -> str:
    lines = [
        "# Firmware Integration Patch",
        "",
        f"- Root: `{preview['root']}`",
        f"- Feature: {preview['feature']}",
        f"- Module: `app_{preview['module']}`",
        f"- Status: `{preview['status']}`",
        f"- Written: {preview.get('written', False)}",
        "",
        "## Targets",
        "",
    ]
    for target in preview.get("targets", []):
        lines.append(f"- `{target.get('status', '')}` `{target.get('path', '')}`: {target.get('reason', '')}")
    for target in preview.get("targets", []):
        if target.get("diff_preview"):
            lines.extend(["", f"## Diff: `{target.get('path', '')}`", "", "```diff", target["diff_preview"], "```"])
    lines.extend(["", "## Policy", ""])
    policy = preview.get("write_policy", {})
    lines.append(f"- Only USER CODE blocks: {policy.get('only_user_code_blocks', False)}")
    for item in policy.get("allowed_paths", []):
        lines.append(f"- allowed: `{item}`")
    lines.extend(["", "## Next Actions", ""])
    for item in preview.get("next_actions", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or write safe app-layer firmware patch files")
    parser.add_argument("--root", default=".")
    parser.add_argument("--feature", required=True)
    parser.add_argument("--pin", default="")
    parser.add_argument("--function", default="")
    parser.add_argument("--no-rtos", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--integrate", action="store_true", help="Patch CubeMX USER CODE sections to include/init/start the generated app module")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if args.integrate:
        preview = preview_integration_patch(
            Path(args.root),
            feature=args.feature,
            pin=args.pin,
            function=args.function,
            rtos=not args.no_rtos,
        )
        result = write_integration_patch(preview, confirm_write=args.confirm_write) if args.write else preview
        markdown = render_integration_markdown(result)
    else:
        preview = preview_patch(
            Path(args.root),
            feature=args.feature,
            pin=args.pin,
            function=args.function,
            rtos=not args.no_rtos,
        )
        result = write_patch(preview, confirm_write=args.confirm_write) if args.write else preview
        markdown = render_markdown(result)
    content = json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else markdown
    if args.out:
        safe_io.safe_write_text(Path(args.out), content, allowed_roots=runtime_context.allowed_write_roots())
    else:
        print(content)


if __name__ == "__main__":
    main()
