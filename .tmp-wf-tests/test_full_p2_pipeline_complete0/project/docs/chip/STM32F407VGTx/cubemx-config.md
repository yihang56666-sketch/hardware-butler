# CubeMX Configuration Notes

- Part: `STM32F407VGTx`
- Board: unknown

## Pin Requests

No pin requests recorded yet.

## Configuration Evidence

- CubeMX `.ioc`: unknown
- Schematic cross-check: unknown
- Datasheet/reference manual cross-check: unknown

## Rules

- Use `python tools\hardware_butler.py advise-pin --root <project> --pin <pin> --function <function>` before changing CubeMX settings.
- Mark alternate-function availability as `needs verification` unless confirmed by package pin data or the existing `.ioc`.
- Keep SWD/JTAG, boot, reset, oscillator, and power pins recoverable during bring-up.
