/*
 * MIT License
 *
 * Copyright (c) 2026 David Reguera Garcia (aka Dreg)
 * dreg@rootkit.es - https://github.com/therealdreg/abductor
 *
 * Disclaimer: this is the work of a hobbyist, shared in good faith for educational
 * purposes. It is not professional work and may contain mistakes or inaccuracies;
 * corrections and feedback are welcome. Provided "as is" and used at your own risk.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

/*
 * Abductor signal validation: blink LED1/LED2/LED3 on the CW312T-SAM4S in sequence.
 * From the CW312T-SAM4S schematic: LED1 = PA16, LED2 = PA15, LED3 = PA14.
 * Watching the three target LEDs blink in turn validates that the Abductor routes
 * the LED1/LED2/LED3 lines from the SAM4S (CW312 edge) to the CW308 UFO.
 */
#include "hal.h"
#include <stdint.h>
#include "gpio.h"
#include "pio.h"

#define LED1 PIO_PA16_IDX
#define LED2 PIO_PA15_IDX
#define LED3 PIO_PA14_IDX

static void dly(volatile uint32_t n){ while(n--){ __asm__ volatile("nop"); } }

int main(void)
{
    platform_init();
    gpio_configure_pin(LED1, PIO_OUTPUT_0 | PIO_DEFAULT);
    gpio_configure_pin(LED2, PIO_OUTPUT_0 | PIO_DEFAULT);
    gpio_configure_pin(LED3, PIO_OUTPUT_0 | PIO_DEFAULT);

    while(1){
        gpio_set_pin_high(LED1); dly(1000000); gpio_set_pin_low(LED1);
        gpio_set_pin_high(LED2); dly(1000000); gpio_set_pin_low(LED2);
        gpio_set_pin_high(LED3); dly(1000000); gpio_set_pin_low(LED3);
        dly(1000000);
    }
}
