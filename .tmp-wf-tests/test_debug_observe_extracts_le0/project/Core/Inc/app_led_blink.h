#ifndef APP_LED_BLINK_H
#define APP_LED_BLINK_H

#include "main.h"
#include <stdint.h>

typedef enum
{
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
