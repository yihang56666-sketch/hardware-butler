#include "app_led_blink.h"
#include "cmsis_os.h"

static uint8_t app_led_blink_enabled;

void app_led_blink_init(void)
{
    app_led_blink_enabled = 0U;
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, GPIO_PIN_RESET);
}

void app_led_blink_start(void)
{
    app_led_blink_enabled = 1U;
}

void app_led_blink_set(uint8_t enabled)
{
    app_led_blink_enabled = enabled ? 1U : 0U;
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, app_led_blink_enabled ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void app_led_blink_task(void const *argument)
{
    (void)argument;
    app_led_blink_init();
    app_led_blink_start();
    for (;;)
    {
        app_led_blink_set(1U);
        osDelay(500U);
        app_led_blink_set(0U);
        osDelay(500U);
    }
}
