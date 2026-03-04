/*
 * sensor_display.c
 *
 *  Created on: Mar 4, 2026
 *      Author: muham
 */

#include "sensor_display.h"
#include "liquidcrystal_i2c.h"
#include "string.h"
#include "stdio.h"
#include "main.h"

extern TIM_HandleTypeDef htim2;

static uint32_t pulse_start = 0;
static uint32_t pulse_end   = 0;
static uint32_t pulse_width = 0;
static char     display_buf[32];

static void delay_us(uint16_t us) {
    // Simple busy wait using DWT cycle counter
    // At 180MHz, 180 cycles = 1us
    uint32_t cycles = us * 180;
    uint32_t start = DWT->CYCCNT;
    while ((DWT->CYCCNT - start) < cycles);
}

static float HCSR04_Read(void) {
    HAL_GPIO_WritePin(TRIG_GPIO_Port, TRIG_Pin, GPIO_PIN_SET);
    delay_us(10);
    HAL_GPIO_WritePin(TRIG_GPIO_Port, TRIG_Pin, GPIO_PIN_RESET);

    __HAL_TIM_SET_COUNTER(&htim2, 0);

    uint32_t timeout = HAL_GetTick();
    while (HAL_GPIO_ReadPin(ECHO_GPIO_Port, ECHO_Pin) == GPIO_PIN_RESET) {
        if (HAL_GetTick() - timeout > 50) return -1;
    }
    pulse_start = __HAL_TIM_GET_COUNTER(&htim2);

    timeout = HAL_GetTick();
    while (HAL_GPIO_ReadPin(ECHO_GPIO_Port, ECHO_Pin) == GPIO_PIN_SET) {
        if (HAL_GetTick() - timeout > 50) return -1;
    }
    pulse_end = __HAL_TIM_GET_COUNTER(&htim2);

    pulse_width = pulse_end - pulse_start;
    return (float)pulse_width / 58.0f;
}
void SensorDisplay_Init(void) {
    // Enable DWT cycle counter for delay_us
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    HD44780_Init(2);
    HD44780_Clear();
    HD44780_SetCursor(0, 0);
    HD44780_PrintStr("Distance Sensor");
    HAL_Delay(1000);
    HD44780_Clear();
}

void SensorDisplay_Update(void) {
    float distance_cm = HCSR04_Read();

    HD44780_SetCursor(0, 0);
    HD44780_PrintStr("Distance:       ");

    HD44780_SetCursor(0, 1);
    if (distance_cm < 0) {
        HD44780_PrintStr("Timeout!        ");
    } else if (distance_cm > 400) {
        HD44780_PrintStr("Out of range    ");
    } else {
        snprintf(display_buf, sizeof(display_buf), "%.1f cm         ", distance_cm);
        HD44780_PrintStr(display_buf);
    }
}
