"""Ensure a workflow-owned project is actually compilable end to end.

The firmware_code_patcher writes app_<module>.c/.h under Core/Src and
Core/Inc, but a minimal fixture (or a user-provided skeleton) often has a
stub main.c that never calls the generated module, and no main.h. This
module closes that gap without ever clobbering a real CubeMX main.c:

- stub main.c (no USER CODE blocks, no MX_ init calls, tiny)  -> replaced
  with a generated main that includes + init + start + run the app module
- real CubeMX main.c (has USER CODE blocks)                   -> the app
  include/init/start lines are inserted into the existing blocks
- custom main.c without USER CODE blocks                      -> left
  untouched (recorded, user integrates manually)

All writes go through safe_io with runtime_context allowed roots, with
backup of any replaced file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firmware_code_patcher  # noqa: E402
import runtime_context  # noqa: E402
import safe_io  # noqa: E402

STUB_MAX_BYTES = 512


def hal_header_for_part(part: str) -> str:
    """Map an STM32 part number to its HAL header (stm32f4xx_hal.h style)."""
    match = re.search(r"STM32([A-Z])(\d)", part.upper())
    if not match:
        raise ValueError(f"cannot infer HAL family header for part: {part!r}")
    family = f"{match.group(1).lower()}{match.group(2)}"
    return f"stm32{family}xx_hal.h"


def classify_main_c(text: str) -> str:
    """Classify Core/Src/main.c as stub | cubemx | custom."""
    if "USER CODE BEGIN" in text:
        return "cubemx"
    if re.search(r"\bMX_\w+_Init\s*\(", text):
        return "custom"
    stripped = text.strip()
    if len(stripped.encode("utf-8", errors="replace")) <= STUB_MAX_BYTES and "app_" not in text:
        return "stub"
    return "custom"


def render_main_h(part: str) -> str:
    guard = "MAIN_H"
    return f"""#ifndef {guard}
#define {guard}

#include "{hal_header_for_part(part)}"
#include <stdint.h>

#endif
"""


def render_main_c(module: str, *, rtos: bool) -> str:
    """Render Core/Src/main.c. Bare-metal calls the app task directly from
    main; RTOS runs it as a CMSIS-RTOS v1 thread instead."""
    if rtos:
        return f"""#include "main.h"
#include "cmsis_os.h"
#include "app_{module}.h"

void Error_Handler(void);
extern void xPortSysTickHandler(void);

/* CubeMX projects define the thread in freertos.c; a scaffold-owned project
   has none, so the app task is the default thread here. */
osThreadDef(appTask, app_{module}_task, osPriorityNormal, 0, 512);

int main(void)
{{
    HAL_Init();
    /* FreeRTOS requires the RTOS tick at the lowest interrupt priority so
       ISRs may call FromISR APIs; re-run HAL tick setup with that priority. */
    HAL_InitTick(15U);

    osThreadCreate(osThread(appTask), NULL);
    osKernelStart();

    /* Unreachable; keeps compilers and static checkers quiet. */
    Error_Handler();
    for (;;)
    {{
    }}
}}

/* SysTick serves both the HAL tick and the FreeRTOS tick: the CMSIS-RTOS
   port implements xPortSysTickHandler; chaining it after HAL_IncTick keeps
   HAL_GetTick working without moving the HAL timebase to a timer. */
void SysTick_Handler(void)
{{
    HAL_IncTick();
    xPortSysTickHandler();
}}

/* FreeRTOS stack-overflow hook (required because FreeRTOSConfig.h sets
   configCHECK_FOR_STACK_OVERFLOW 2); routes into Error_Handler. */
void vApplicationStackOverflowHook(void *xTask, char *pcTaskName)
{{
    (void)xTask;
    (void)pcTaskName;
    Error_Handler();
}}

void Error_Handler(void)
{{
    __disable_irq();
    for (;;)
    {{
    }}
}}
"""
    return f"""#include "main.h"
#include "app_{module}.h"

void Error_Handler(void);

int main(void)
{{
    HAL_Init();

    /* App module bring-up. The app task loop never returns. */
    app_{module}_init();
    app_{module}_start();
    app_{module}_task((void const *)NULL);

    /* Unreachable; keeps compilers and static checkers quiet. */
    Error_Handler();
    for (;;)
    {{
    }}
}}

void Error_Handler(void)
{{
    __disable_irq();
    for (;;)
    {{
    }}
}}
"""


def render_rtt_h() -> str:
    return """#ifndef APP_RTT_H
#define APP_RTT_H

#include <stdint.h>

/* Minimal RTT up-channel writer. Host debuggers (probe-rs `rtt`, pyOCD
   `rtt`) discover the control block by scanning RAM for the "SEGGER RTT"
   magic, so no peripheral or probe-side registration is needed. */

#ifdef __cplusplus
extern "C" {
#endif

void app_rtt_write(const char *data, uint32_t len);
void app_rtt_puts(const char *s);

#ifdef __cplusplus
}
#endif

#endif /* APP_RTT_H */
"""


def render_rtt_c() -> str:
    """Clean-room minimal implementation of the public RTT write-side
    contract (SEGGER's documented control-block layout + up-buffer ring
    semantics). Drop-on-full: unread data is never overwritten, so the host
    reader's offsets stay consistent."""
    return """#include "app_rtt.h"

#include <string.h>

#define APP_RTT_UP_BUFFER_SIZE 1024U
#define APP_RTT_ID "SEGGER RTT\\0"

typedef struct {
    char *pBuffer;
    uint32_t SizeOfBuffer;
    volatile uint32_t WrOff;
    volatile uint32_t RdOff;
    volatile uint32_t Flags;
} app_rtt_buffer_desc;

typedef struct {
    char acID[16];
    uint32_t MaxNumUpBuffers;
    uint32_t MaxNumDownBuffers;
    app_rtt_buffer_desc aUp[1];
    app_rtt_buffer_desc aDown[1];
} app_rtt_control_block;

static char app_rtt_up_storage[APP_RTT_UP_BUFFER_SIZE];
static char app_rtt_down_storage[16];

/* `used` keeps the block in the image even if the compiler sees no readers:
   the host debugger reads it out-of-band via SWD. */
static app_rtt_control_block app_rtt_cb __attribute__((used)) = {
    .acID = APP_RTT_ID,
    .MaxNumUpBuffers = 1U,
    .MaxNumDownBuffers = 1U,
    .aUp = {
        {
            .pBuffer = app_rtt_up_storage,
            .SizeOfBuffer = APP_RTT_UP_BUFFER_SIZE,
            .WrOff = 0U,
            .RdOff = 0U,
            .Flags = 0U,
        },
    },
    .aDown = {
        {
            .pBuffer = app_rtt_down_storage,
            .SizeOfBuffer = (uint32_t)sizeof(app_rtt_down_storage),
            .WrOff = 0U,
            .RdOff = 0U,
            .Flags = 0U,
        },
    },
};

void app_rtt_write(const char *data, uint32_t len)
{
    uint32_t written = 0U;
    if ((data == (void *)0) || (len == 0U))
    {
        return;
    }
    while (written < len)
    {
        uint32_t wr = app_rtt_cb.aUp[0].WrOff;
        uint32_t rd = app_rtt_cb.aUp[0].RdOff;
        uint32_t space = (rd > wr)
            ? (rd - wr - 1U)
            : (APP_RTT_UP_BUFFER_SIZE - (wr - rd) - 1U);
        if (space == 0U)
        {
            break; /* full: drop the rest rather than overwrite unread data */
        }
        uint32_t chunk = (len - written) < space ? (len - written) : space;
        uint32_t first = APP_RTT_UP_BUFFER_SIZE - wr;
        if (first > chunk)
        {
            first = chunk;
        }
        (void)memcpy(&app_rtt_up_storage[wr], &data[written], first);
        (void)memcpy(&app_rtt_up_storage[0], &data[written + first], chunk - first);
        written += chunk;
        app_rtt_cb.aUp[0].WrOff = (wr + chunk) % APP_RTT_UP_BUFFER_SIZE;
    }
}

void app_rtt_puts(const char *s)
{
    if (s == (void *)0)
    {
        return;
    }
    app_rtt_write(s, (uint32_t)strlen(s));
}
"""


def render_freertos_config_h() -> str:
    """Minimal CMSIS-RTOS v1 compatible FreeRTOSConfig.h (CubeMX puts it in
    Core/Inc, which the PlatformIO build already adds via -ICore/Inc).

    configCPU_CLOCK_HZ defaults to the 16 MHz HSI the chip runs on when no
    SystemClock_Config runs (scaffold-owned projects); CubeMX projects keep
    their own generated config (scaffold never overwrites an existing one).
    SVC/PendSV are aliased here; SysTick is NOT aliased because the
    generated main.c chains HAL_IncTick + xPortSysTickHandler manually.
    """
    return """#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

/* Auto-generated by hardware_butler firmware_project_scaffold. */

#define configUSE_PREEMPTION              1
#define configUSE_IDLE_HOOK               0
#define configUSE_TICK_HOOK               0
#define configCPU_CLOCK_HZ                ( 16000000UL )
#define configTICK_RATE_HZ                ( ( TickType_t ) 1000 )
#define configMAX_PRIORITIES              ( 7 )
#define configMINIMAL_STACK_SIZE          ( ( uint16_t ) 128 )
#define configTOTAL_HEAP_SIZE             ( ( size_t ) ( 16 * 1024 ) )
#define configMAX_TASK_NAME_LEN           ( 16 )
#define configUSE_16_BIT_TICKS            0
#define configIDLE_SHOULD_YIELD           1
#define configUSE_MUTEXES                  1
#define configUSE_RECURSIVE_MUTEXES        1
#define configUSE_COUNTING_SEMAPHORES     1
#define configQUEUE_REGISTRY_SIZE         8
#define configCHECK_FOR_STACK_OVERFLOW    2
#define configUSE_MALLOC_FAILED_HOOK      0
#define configUSE_TIMERS                  1
#define configTIMER_TASK_PRIORITY         ( 2 )
#define configTIMER_QUEUE_LENGTH          10
#define configTIMER_TASK_STACK_DEPTH      ( configMINIMAL_STACK_SIZE * 2 )
#define configSUPPORT_STATIC_ALLOCATION   0
#define configSUPPORT_DYNAMIC_ALLOCATION  1

/* Cortex-M specific. */
#ifdef __NVIC_PRIO_BITS
#define configPRIO_BITS                   __NVIC_PRIO_BITS
#else
#define configPRIO_BITS                   4
#endif
#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY       15
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY  5
#define configKERNEL_INTERRUPT_PRIORITY \\
    ( configLIBRARY_LOWEST_INTERRUPT_PRIORITY << ( 8 - configPRIO_BITS ) )
#define configMAX_SYSCALL_INTERRUPT_PRIORITY \\
    ( configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << ( 8 - configPRIO_BITS ) )

/* Definitions that map the FreeRTOS port interrupt handlers to their CMSIS
   standard names. SysTick is chained in main.c instead (see render_main_c). */
#define vPortSVCHandler                    SVC_Handler
#define xPortPendSVHandler                 PendSV_Handler

#endif /* FREERTOS_CONFIG_H */
"""


def _insertion_lines(module: str, *, rtos: bool) -> list[dict[str, str]]:
    lines = [
        {"block": "Includes", "code": f'#include "app_{module}.h"', "reason": "Include app module API."},
        {"block": "2", "code": f"app_{module}_init();", "reason": "Initialize app module after CubeMX init."},
        {"block": "2", "code": f"app_{module}_start();", "reason": "Start the app module."},
        {"block": "4", "code": f"app_{module}_task(NULL);", "reason": "Run the app module task loop."},
    ]
    return lines


def _apply_cubemx_insertions(main_text: str, module: str) -> tuple[str, list[dict[str, str]]]:
    applied: list[dict[str, str]] = []
    updated = main_text
    for item in _insertion_lines(module, rtos=False):
        before = updated
        updated = firmware_code_patcher.insert_into_user_code_block(updated, item["block"], item["code"])
        if updated != before:
            applied.append(item)
    return updated, applied


def ensure_compilable(
    root: Path,
    *,
    part: str,
    module: str,
    rtos: bool = False,
) -> dict[str, Any]:
    """Make the project compile-ready for the generated app module.

    Returns an evidence dict; never raises for per-file issues (recorded
    under files_skipped). Requires `part` to infer the HAL header.
    """
    root = root.resolve()
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "ok",
        "root": str(root),
        "part": part,
        "module": module,
        "files_written": [],
        "files_skipped": [],
        "actions": [],
    }
    if not part:
        result["status"] = "blocked-needs-input"
        result["error"] = "scaffold requires a chip part to infer the HAL header"
        return result
    try:
        hal_header_for_part(part)
    except ValueError as exc:
        result["status"] = "blocked-needs-input"
        result["error"] = str(exc)
        return result

    allowed_roots = runtime_context.allowed_write_roots(root)

    rtt_h = root / "Core" / "Inc" / "app_rtt.h"
    rtt_c = root / "Core" / "Src" / "app_rtt.c"
    if not rtt_c.exists():
        try:
            safe_io.safe_write_text(rtt_h, render_rtt_h(), allowed_roots=allowed_roots)
            safe_io.safe_write_text(rtt_c, render_rtt_c(), allowed_roots=allowed_roots)
            result["files_written"].extend([str(rtt_h), str(rtt_c)])
            result["actions"].append(
                "created Core/{Inc,Src}/app_rtt.{h,c} (RTT observability; probe-rs/pyOCD auto-discover)"
            )
        except Exception as exc:  # noqa: BLE001
            result["files_skipped"].append({"path": str(rtt_c), "reason": str(exc)})

    if rtos:
        freertos_cfg = root / "Core" / "Inc" / "FreeRTOSConfig.h"
        if not freertos_cfg.exists():
            try:
                safe_io.safe_write_text(
                    freertos_cfg, render_freertos_config_h(), allowed_roots=allowed_roots
                )
                result["files_written"].append(str(freertos_cfg))
                result["actions"].append("created Core/Inc/FreeRTOSConfig.h (CMSIS-RTOS v1)")
            except Exception as exc:  # noqa: BLE001
                result["files_skipped"].append({"path": str(freertos_cfg), "reason": str(exc)})

    main_h = root / "Core" / "Inc" / "main.h"
    if not main_h.exists():
        try:
            safe_io.safe_write_text(main_h, render_main_h(part), allowed_roots=allowed_roots)
            result["files_written"].append(str(main_h))
            result["actions"].append("created main.h")
        except Exception as exc:  # noqa: BLE001
            result["files_skipped"].append({"path": str(main_h), "reason": str(exc)})

    main_c = root / "Core" / "Src" / "main.c"
    if not main_c.exists():
        try:
            safe_io.safe_write_text(
                main_c, render_main_c(module, rtos=rtos), allowed_roots=allowed_roots
            )
            result["files_written"].append(str(main_c))
            result["actions"].append("created main.c calling app module")
        except Exception as exc:  # noqa: BLE001
            result["files_skipped"].append({"path": str(main_c), "reason": str(exc)})
        return result

    original = main_c.read_text(encoding="utf-8", errors="replace")
    kind = classify_main_c(original)
    result["main_c_class"] = kind
    if kind == "stub":
        try:
            safe_io.safe_write_text(
                main_c, render_main_c(module, rtos=rtos), allowed_roots=allowed_roots, backup_existing=True
            )
            result["files_written"].append(str(main_c))
            result["actions"].append("replaced stub main.c with generated main calling app module")
        except Exception as exc:  # noqa: BLE001
            result["files_skipped"].append({"path": str(main_c), "reason": str(exc)})
    elif kind == "cubemx":
        updated, applied = _apply_cubemx_insertions(original, module)
        if applied:
            try:
                safe_io.safe_write_text(
                    main_c, updated, allowed_roots=allowed_roots, backup_existing=True
                )
                result["files_written"].append(str(main_c))
                result["actions"].append(
                    "inserted app include/init/start/task into CubeMX USER CODE blocks: "
                    + ", ".join(f"{item['block']}:{item['code']}" for item in applied)
                )
            except Exception as exc:  # noqa: BLE001
                result["files_skipped"].append({"path": str(main_c), "reason": str(exc)})
        else:
            missing_blocks = [
                item["block"] for item in _insertion_lines(module, rtos=False)
                if not firmware_code_patcher.user_code_block_exists(original, item["block"])
            ]
            result["actions"].append("app already integrated or blocks missing: " + ", ".join(missing_blocks))
    else:
        result["actions"].append("custom main.c left untouched; integrate app module manually")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure workflow project is compilable for the app module")
    parser.add_argument("--root", default=".")
    parser.add_argument("--part", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--rtos", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = ensure_compilable(Path(args.root), part=args.part, module=args.module, rtos=args.rtos)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
