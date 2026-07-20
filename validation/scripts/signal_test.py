#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2026 David Reguera Garcia (aka Dreg)
# dreg@rootkit.es - https://github.com/therealdreg/abductor
#
# Disclaimer: this is the work of a hobbyist, shared in good faith for educational
# purposes. It is not professional work and may contain mistakes or inaccuracies;
# corrections and feedback are welcome. Provided "as is" and used at your own risk.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Abductor signal-validation runner.

Flashes one of the test firmwares in dregdoc/scripts/firmware/ via SAM-BA, then reads the exercised
signal back through the ChipWhisperer to confirm the Abductor routes it.

Build the firmware first (the firmware dirs live under chipwhisperer/firmware/mcu/):
    cd firmware/mcu/led-blink       && make PLATFORM=CW312_SAM4S CRYPTO_TARGET=NONE SS_VER=SS_VER_2_1
    cd firmware/mcu/abductor-sigtest && make PLATFORM=CW312_SAM4S CRYPTO_TARGET=NONE SS_VER=SS_VER_2_1
(A copy of each firmware source + makefile is kept next to this script under firmware/.)

Usage:
    signal_test.py <firmware.hex> led     # LED1/2/3 (PA16/PA15/PA14): watch the target LEDs blink in turn
    signal_test.py <firmware.hex> gpio3   # GPIO3 (PA8): read TIO3 toggling on the CW (indicates routing)

Pin map (from the CW312T-SAM4S schematic): LED1=PA16, LED2=PA15, LED3=PA14, GPIO3=PA8,
CLKOUT/CLK_FROM_SAM=PA6 (PCK0), trigger/GPIO4=PA7, UART=PA9/PA10, CLKIN=XIN/PB9.
"""
import sys, time
import chipwhisperer as cw

HEX  = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else 'gpio3'

scope = cw.scope(); scope.default_setup()
for k in range(3):
    try:
        cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print('FLASHED'); break
    except Exception as e:
        print('flash retry:', str(e)[:60]); time.sleep(1.0)
scope.io.nrst = 'low'; time.sleep(0.05); scope.io.nrst = 'high_z'; time.sleep(0.3)

if MODE == 'gpio3':
    scope.io.tio3 = 'high_z'; seen = set()
    for i in range(16):
        st = scope.io.tio_states; seen.add(int(st[2]))
        print('t=%4.1fs  TIO(1,2,3,4)=%s' % (i * 0.35, st)); time.sleep(0.35)
    print('=> GPIO3/TIO3 seen', sorted(seen), '->',
          'TOGGLES = ROUTED OK' if len(seen) > 1 else 'STUCK (check SJ1 / routing)')
elif MODE == 'led':
    print('Watch the CW308 target LEDs: LED1(PA16) -> LED2(PA15) -> LED3(PA14) in sequence.')
    time.sleep(6)

scope.dis()
