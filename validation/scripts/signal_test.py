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
Abductor signal test on the CW312T-SAM4S with a ChipWhisperer Husky Plus: flash a test firmware
over SAM-BA, then check the signal it drives. It runs the same way on the straight board, the
right-angle board and the CW313.

The firmware sources and makefiles are in firmware/ next to this script. Their makefiles include
files from the chipwhisperer firmware tree, so copy each folder into chipwhisperer/firmware/mcu/
and build it there:
    cd firmware/mcu/led-blink       && make PLATFORM=CW312_SAM4S CRYPTO_TARGET=NONE SS_VER=SS_VER_2_1
    cd firmware/mcu/abductor-sigtest && make PLATFORM=CW312_SAM4S CRYPTO_TARGET=NONE SS_VER=SS_VER_2_1
Each build writes led-blink-CW312_SAM4S.hex or abductor-sigtest-CW312_SAM4S.hex in its folder.

Usage (the hex path is required; the mode defaults to gpio3):
    signal_test.py <firmware.hex> led     # led-blink: watch LED1/2/3 (PA16/PA15/PA14) blink in turn
    signal_test.py <firmware.hex> gpio3   # abductor-sigtest: read GPIO3 (PA8) back as TIO3

led only flashes the firmware and waits 6 s while you watch the LEDs. gpio3 reads TIO3 16 times,
0.35 s apart: seeing both 0 and 1 shows that GPIO3 is routed to TIO3. Results go to the console.

Pin map (from the CW312T-SAM4S schematic): LED1=PA16, LED2=PA15, LED3=PA14, GPIO3=PA8,
CLKOUT/CLK_FROM_SAM=PA6 (PCK0), trigger/GPIO4=PA7, UART=PA9/PA10, CLKIN=XIN/PB9.
"""
import sys, time
import chipwhisperer as cw

HEX  = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else 'gpio3'

scope = cw.scope(); scope.default_setup()
# Up to 3 programming tries, 1 s apart; if all fail, the script stops with exit status 2.
for k in range(3):
    try:
        cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print('FLASHED'); break
    except Exception as e:
        print('flash retry:', str(e)[:60]); time.sleep(1.0)
else:
    print('!!! SAM-BA programming failed after retries. Please reconnect the Husky USB.'); scope.dis(); raise SystemExit(2)
# Pulse nRST low for 50 ms, release it and give the firmware 300 ms to start.
scope.io.nrst = 'low'; time.sleep(0.05); scope.io.nrst = 'high_z'; time.sleep(0.3)

if MODE == 'gpio3':
    # TIO3 as a high-Z input, so it only follows what the target drives on GPIO3.
    scope.io.tio3 = 'high_z'; seen = set()
    for i in range(16):
        # tio_states is (TIO1, TIO2, TIO3, TIO4), so st[2] is TIO3.
        st = scope.io.tio_states; seen.add(int(st[2]))
        print('t=%4.1fs  TIO(1,2,3,4)=%s' % (i * 0.35, st)); time.sleep(0.35)
    # SJ1 is not on the GPIO3 path: it only selects whether ERASE/PB12 follows PDIC (the default,
    # which SAM-BA programming needs) or GPIO3, so a stuck TIO3 points at the GPIO3 routing.
    print('=> GPIO3/TIO3 seen', sorted(seen), '->',
          'TOGGLES = ROUTED OK' if len(seen) > 1 else 'STUCK (check the GPIO3 routing)')
elif MODE == 'led':
    # Nothing to read back: the LED check is visual.
    print('Watch the CW308 target LEDs: LED1(PA16) -> LED2(PA15) -> LED3(PA14) in sequence.')
    time.sleep(6)

scope.dis()
