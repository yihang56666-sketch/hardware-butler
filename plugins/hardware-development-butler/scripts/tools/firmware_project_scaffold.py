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
    task_arg = "NULL" if not rtos else "NULL"
    return f"""#include "main.h"
#include "app_{module}.h"

void Error_Handler(void);

int main(void)
{{
    HAL_Init();

    /* App module bring-up. The app task loop never returns. */
    app_{module}_init();
    app_{module}_start();
    app_{module}_task((void const *){task_arg});

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
