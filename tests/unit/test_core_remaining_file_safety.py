from __future__ import annotations

from pathlib import Path

import firmware_code_patcher as patcher
import firmware_project_scaffold as scaffold
import pytest

CUBEMX_MAIN = """/* USER CODE BEGIN Includes */
/* USER CODE END Includes */
int main(void) {
    HAL_Init();
    /* USER CODE BEGIN 2 */
    /* USER CODE END 2 */
    while (1) {
        /* USER CODE BEGIN 3 */
        /* USER CODE END 3 */
    }
}
/* USER CODE BEGIN 4 */
/* USER CODE END 4 */
"""


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HW_BUTLER_ROOT", str(tmp_path))


def make_project(tmp_path: Path, main_text: str | None = None) -> Path:
    root = tmp_path / "project"
    (root / "Core" / "Src").mkdir(parents=True)
    (root / "Core" / "Inc").mkdir()
    (root / "board.ioc").write_text("Mcu.Name=STM32F407VGTx\n", encoding="utf-8")
    if main_text is not None:
        (root / "Core" / "Src" / "main.c").write_text(main_text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "source",
    [
        "int main(void) { user_init(); for (;;) { user_tick(); } }\n",
        "int important = 7;\nint main(void) { while (1) {} }\n",
        "int main(void) { return application(); }\n",
    ],
)
def test_scaffold_does_not_classify_short_user_code_as_stub(source: str) -> None:
    assert scaffold.classify_main_c(source) == "custom"


def test_scaffold_preserves_small_custom_main_and_reports_manual_integration(tmp_path: Path) -> None:
    original = "int main(void) { user_init(); for (;;) { user_tick(); } }\n"
    root = make_project(tmp_path, original)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    assert (root / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == original
    assert result["status"] == "needs-manual-integration"


@pytest.mark.parametrize("existing", ["Core/Inc/app_rtt.h", "Core/Src/app_rtt.c"])
def test_scaffold_preserves_each_existing_rtt_file_and_creates_its_missing_peer(
    tmp_path: Path, existing: str
) -> None:
    root = make_project(tmp_path)
    original = "user-owned RTT implementation\n"
    (root / existing).write_text(original, encoding="utf-8")
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    assert (root / existing).read_text(encoding="utf-8") == original
    assert (root / "Core/Inc/app_rtt.h").is_file()
    assert (root / "Core/Src/app_rtt.c").is_file()
    assert str(root / existing) not in result["files_written"]


def test_scaffold_write_failure_is_not_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_project(tmp_path)
    real_write = scaffold.safe_io.safe_write_text

    def fail_main_header(path: Path, *args, **kwargs):
        if path.name == "main.h":
            raise PermissionError("fixture: main.h is not writable")
        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(scaffold.safe_io, "safe_write_text", fail_main_header)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    assert result["status"] == "error"
    assert any(item["path"].endswith("main.h") for item in result["files_skipped"])


def test_scaffold_read_failure_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_project(tmp_path, CUBEMX_MAIN)
    main_path = root / "Core/Src/main.c"
    real_read = Path.read_text

    def fail_main_read(path: Path, *args, **kwargs):
        if path == main_path:
            raise PermissionError("fixture: main.c is not readable")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_main_read)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    assert result["status"] == "error"
    assert any(item["path"] == str(main_path) for item in result["files_skipped"])


@pytest.mark.parametrize("module", ["../outside", 'led"\n#error injected', ""])
def test_scaffold_rejects_invalid_module_before_writing(tmp_path: Path, module: str) -> None:
    root = make_project(tmp_path)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module=module)
    assert result["status"] == "blocked-needs-input"
    assert result["files_written"] == []
    assert list((root / "Core/Src").iterdir()) == []
    assert list((root / "Core/Inc").iterdir()) == []


def test_scaffold_places_bare_metal_task_in_loop_not_global_block(tmp_path: Path) -> None:
    root = make_project(tmp_path, CUBEMX_MAIN)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    updated = (root / "Core/Src/main.c").read_text(encoding="utf-8")
    loop_body = updated.split("/* USER CODE BEGIN 3 */")[1].split("/* USER CODE END 3 */")[0]
    global_body = updated.split("/* USER CODE BEGIN 4 */")[1].split("/* USER CODE END 4 */")[0]
    assert "app_led_task(NULL);" in loop_body
    assert "app_led_task(NULL);" not in global_body
    assert result["status"] == "ok"


def test_scaffold_missing_loop_block_does_not_claim_complete_integration(tmp_path: Path) -> None:
    original = CUBEMX_MAIN.replace("/* USER CODE BEGIN 3 */", "").replace("/* USER CODE END 3 */", "")
    root = make_project(tmp_path, original)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led")
    assert result["status"] == "needs-manual-integration"
    assert (root / "Core/Src/main.c").read_text(encoding="utf-8") == original


def test_scaffold_does_not_call_rtos_task_as_bare_metal_in_cubemx(tmp_path: Path) -> None:
    root = make_project(tmp_path, CUBEMX_MAIN)
    result = scaffold.ensure_compilable(root, part="STM32F407VGTx", module="led", rtos=True)
    assert result["status"] == "needs-manual-integration"
    assert (root / "Core/Src/main.c").read_text(encoding="utf-8") == CUBEMX_MAIN


@pytest.mark.parametrize("relative_path", ["Drivers/user.c", "Core/Src/main.c", ".embeddedskills/config.json"])
def test_patch_prevalidates_all_paths_before_modifying_any_file(tmp_path: Path, relative_path: str) -> None:
    root = make_project(tmp_path)
    forbidden = root / relative_path
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_text("keep user file\n", encoding="utf-8")
    preview = patcher.preview_patch(root, feature="led", function="gpio-output", rtos=False)
    preview["files"].append({"path": str(forbidden), "content": "clobbered\n"})
    with pytest.raises(ValueError):
        patcher.write_patch(preview, confirm_write=True)
    assert forbidden.read_text(encoding="utf-8") == "keep user file\n"
    assert not (root / "Core/Inc/app_led.h").exists()
    assert not (root / "Core/Src/app_led.c").exists()


def test_patch_cannot_write_to_another_project_in_the_same_workspace(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    other = tmp_path / "other-project"
    other.mkdir()
    target = other / "source.c"
    target.write_text("other project\n", encoding="utf-8")
    preview = patcher.preview_patch(root, feature="led", function="gpio-output", rtos=False)
    preview["files"].append({"path": str(target), "content": "clobbered\n"})
    with pytest.raises(ValueError):
        patcher.write_patch(preview, confirm_write=True)
    assert target.read_text(encoding="utf-8") == "other project\n"
    assert not (root / "Core/Inc/app_led.h").exists()


def integration_preview(tmp_path: Path) -> tuple[Path, dict]:
    root = make_project(tmp_path, CUBEMX_MAIN)
    preview = patcher.preview_patch(root, feature="led", function="gpio-output", rtos=False)
    patcher.write_patch(preview, confirm_write=True)
    return root, patcher.preview_integration_patch(root, feature="led", function="gpio-output", rtos=False)


def test_integration_rejects_changed_file_since_preview(tmp_path: Path) -> None:
    root, preview = integration_preview(tmp_path)
    main_path = root / "Core/Src/main.c"
    changed = CUBEMX_MAIN.replace("HAL_Init();", "user_setup();")
    main_path.write_text(changed, encoding="utf-8")
    with pytest.raises(ValueError, match="changed since preview"):
        patcher.write_integration_patch(preview, confirm_write=True)
    assert main_path.read_text(encoding="utf-8") == changed
    assert not main_path.with_suffix(".c.bak").exists()


def test_integration_rejects_unlisted_target_before_other_changes(tmp_path: Path) -> None:
    root, preview = integration_preview(tmp_path)
    forbidden = root / "Drivers/user.c"
    forbidden.parent.mkdir()
    forbidden.write_text(CUBEMX_MAIN, encoding="utf-8")
    rogue = dict(preview["targets"][0], path=str(forbidden))
    preview["targets"].append(rogue)
    with pytest.raises(ValueError):
        patcher.write_integration_patch(preview, confirm_write=True)
    assert forbidden.read_text(encoding="utf-8") == CUBEMX_MAIN
    assert (root / "Core/Src/main.c").read_text(encoding="utf-8") == CUBEMX_MAIN


def test_patch_still_requires_confirmation(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    preview = patcher.preview_patch(root, feature="led", function="gpio-output", rtos=False)
    with pytest.raises(ValueError, match="confirm-write"):
        patcher.write_patch(preview, confirm_write=False)
    assert not (root / "Core/Inc/app_led.h").exists()
