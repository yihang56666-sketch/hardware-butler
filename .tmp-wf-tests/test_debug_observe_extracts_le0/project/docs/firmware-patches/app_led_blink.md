# Firmware Patch Integration

- Feature: led-blink
- Function: `gpio-output`
- IOC: `D:\一些有用的项目\硬件agent\.tmp-wf-tests\test_debug_observe_extracts_le0\project\Blinky.ioc`
- RTOS requested: True
- RTOS available: True

## Files

- `Core/Inc/app_led_blink.h`
- `Core/Src/app_led_blink.c`

## CubeMX Integration

- Add `#include "app_led_blink.h"` inside a CubeMX `USER CODE BEGIN Includes` block.
- Call `app_led_blink_init()` inside a CubeMX init user-code block after GPIO/peripheral init.
- If FreeRTOS is enabled, create a task that calls `app_led_blink_task` with a conservative priority and stack.
- HAL handle: `needs verification`
- Timeout: 0 ms for blocking HAL calls where applicable.

## Required Hooks

- Call app init after CubeMX peripheral init.
- Create or call app task from a USER CODE section.

## Error And Recovery Policy

- Return contract: app status enum with OK/NOT_READY/TIMEOUT/HAL_ERROR
- Return to inactive output level on stop or fault.

## Safety

- Initialize feature disabled until app explicitly starts it.
- Use inactive output level or zero/safe duty before enabling load.

## Verification

- Build before flashing.
- Keep first firmware test low-risk and observable through UART/RTT/SWO or LED.
- Flash only after hardware action plan reaches ready-for-user-confirmation and user confirms it.
