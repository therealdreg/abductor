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
 * Abductor signal test firmware for the CW312T-SAM4S. It drives three otherwise unused signals that
 * the Abductor has to route (pins from the CW312T-SAM4S schematic):
 *
 *   GPIO3  = PA8   : slow square wave, read back on the Husky Plus as TIO3 (scope.io.tio_states).
 *   CLKOUT = PA6   : PCK0 = MAINCK/8, about 0.92 MHz from the 7.37 MHz clock on XIN. PA6 is
 *                    CLK_FROM_SAM, the target clock-out, which runs from CW312 edge A29 to the
 *                    UFO CLKOUT pin (silkscreen CLKFB).
 *   LED1   = PA16  : follows GPIO3 as a visible sign that the firmware runs (led-blink.c checks
 *                    LED1 to LED3).
 *
 * Reading GPIO3 back on the Husky Plus confirms its routing. CLKOUT (PA6) is best confirmed by
 * continuity on the UFO, because the Husky Plus frequency counter does not read the UFO clock-out
 * path without extra clock-routing setup.
 * Copy this folder into chipwhisperer/firmware/mcu/, build it there with the makefile, and flash it
 * with signal_test.py <hex> gpio3.
 */
#include "hal.h"
#include <stdint.h>
#include "gpio.h"
#include "pio.h"
#include "pmc.h"

#define GPIO3 PIO_PA8_IDX
#define LED1  PIO_PA16_IDX

static void dly(volatile uint32_t n){ while(n--){ __asm__ volatile("nop"); } }

int main(void)
{
    platform_init();

    /* CLKOUT: PCK0 = MAINCK/8 out on PA6 (peripheral B = PCK0) */
    pmc_disable_pck(PMC_PCK_0);
    pmc_switch_pck_to_mainck(PMC_PCK_0, PMC_PCK_PRES_CLK_8);
    pmc_enable_pck(PMC_PCK_0);
    gpio_configure_pin(PIO_PA6_IDX, PIO_PERIPH_B | PIO_DEFAULT);

    /* GPIO3 square wave, mirrored on LED1 */
    gpio_configure_pin(GPIO3, PIO_OUTPUT_0 | PIO_DEFAULT);
    gpio_configure_pin(LED1,  PIO_OUTPUT_0 | PIO_DEFAULT);

    while(1){
        gpio_set_pin_high(GPIO3); gpio_set_pin_high(LED1); dly(3000000);
        gpio_set_pin_low(GPIO3);  gpio_set_pin_low(LED1);  dly(3000000);
    }
}
