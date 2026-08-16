"""LLM-first firmware module generation with template fallback policy.

When the user opts in via .hardware-butler/llm-config.json ({"codegen": true}),
the workflow asks the configured LLM to write the app_<module>.c/.h pair
instead of (or, on failure, falling back to) the deterministic templates in
firmware_code_patcher.

Trust rules:
- The LLM chooses file CONTENTS only. Paths are constructed here
  (Core/Inc/app_<module>.h, Core/Src/app_<module>.c) — never taken from
  the response.
- The response must pass contract validation (required symbols present,
  include guard, no forbidden headers) before it is accepted.
- Any failure returns a structured error; the caller falls back to
  templates so the workflow never breaks because of codegen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firmware_code_patcher  # noqa: E402
import llm_client  # noqa: E402
import llm_config  # noqa: E402

CODEGEN_MAX_TOKENS = 8192


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first complete top-level JSON object from LLM text.

    Brace-depth scanner that is safe for nested braces inside JSON string
    values (e.g. C code) because it tracks string literals and escapes.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except ValueError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def _required_symbols(module: str) -> list[str]:
    return [
        f"app_{module}_init",
        f"app_{module}_start",
        f"app_{module}_set",
        f"app_{module}_task",
        f"APP_{module.upper()}_OK",
    ]


def validate_generated_pair(module: str, header: str, source: str, *, rtos: bool) -> list[str]:
    """Return a list of contract violations (empty list = acceptable)."""
    problems: list[str] = []
    combined = header + "\n" + source
    for symbol in _required_symbols(module):
        if symbol not in combined:
            problems.append(f"missing required symbol: {symbol}")
    guard = f"APP_{module.upper()}_H"
    if guard not in header:
        problems.append(f"header missing include guard {guard}")
    if "main.h" not in source and "main.h" not in header:
        problems.append("neither file includes main.h")
    forbidden = ["Arduino.h", "bsp_|STM32Arduino"]
    if not rtos and ("cmsis_os.h" in combined or "FreeRTOS.h" in combined):
        problems.append("RTOS header used but build is bare-metal")
    for marker in forbidden:
        if marker in combined:
            problems.append(f"forbidden dependency: {marker}")
    if len(source) < 200:
        problems.append("source suspiciously short (<200 chars)")
    return problems


def _datasheet_hint(root: Path, part: str) -> str:
    """Pull a compact datasheet-evidence excerpt for the prompt, if present."""
    path = root / ".hardware-butler" / "datasheet-evidence.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    parameters = data.get("parameters") or {}
    pin_functions = data.get("pin_functions") or {}
    if not parameters and not pin_functions:
        return ""
    return json.dumps({"part": part, "parameters": parameters, "pin_functions": pin_functions}, ensure_ascii=False)


def generate_app_module(
    root: Path,
    *,
    feature: str,
    pin: str,
    function: str,
    part: str,
    hal_handle: str,
    rtos: bool,
    goal: str,
) -> dict[str, Any]:
    """Ask the configured LLM to write the app module.

    Returns one of:
      {"status": "not-enabled"}                     codegen opt-in is off
      {"status": "pending", "task_id": ...}         claude-code host task
      {"status": "error", "error": ...}             any failure (fall back)
      {"status": "ok", "module", "files", "notes"}  validated file pair
    """
    root = root.resolve()
    config = llm_config.load_config(root)
    if not config.codegen:
        return {"status": "not-enabled"}
    if not llm_config.is_configured(config):
        return {"status": "error", "error": "codegen enabled but provider not configured"}

    module = firmware_code_patcher.module_name(feature)
    datasheet_hint = _datasheet_hint(root, part)
    system, prompt = llm_client.generate_module_prompt(
        module,
        feature=feature,
        pin=pin,
        function=function,
        part=part,
        hal_handle=hal_handle,
        rtos=rtos,
        goal=goal,
        datasheet_hint=datasheet_hint,
    )
    # Deterministic per workflow attempt: the codegen prompt embeds the same
    # feature/pin/function inputs across resumes of one firmware-plan pass,
    # so a stable id lets the host-agent response match after --resume.
    # Attempt-scoped inputs (failure patches) change feature/pin and thus
    # the id naturally.
    import hashlib
    seed = json.dumps({"feature": feature, "pin": pin, "function": function, "part": part, "rtos": rtos}, sort_keys=True)
    task_id = f"codegen-{module}-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10]}"
    result = llm_client.call_llm(
        root, config, task_id=task_id, prompt=prompt, system=system, max_tokens=CODEGEN_MAX_TOKENS
    )
    if result.get("status") == "pending":
        return {"status": "pending", "task_id": task_id}
    if result.get("status") != "ok":
        return {"status": "error", "error": str(result.get("error", "llm call failed"))}

    parsed = extract_json_object(result["text"])
    if not parsed:
        return {"status": "error", "error": "response contained no parseable JSON object"}
    header = str(parsed.get("header", "") or "")
    source = str(parsed.get("source", "") or "")
    notes = str(parsed.get("notes", "") or "")
    if not header or not source:
        return {"status": "error", "error": "response JSON missing header/source contents"}

    problems = validate_generated_pair(module, header, source, rtos=rtos)
    if problems:
        return {"status": "error", "error": "contract violations: " + "; ".join(problems)}

    return {
        "status": "ok",
        "module": module,
        "notes": notes,
        "files": [
            {"path": str(root / "Core" / "Inc" / f"app_{module}.h"), "content": header},
            {"path": str(root / "Core" / "Src" / f"app_{module}.c"), "content": source},
        ],
    }
