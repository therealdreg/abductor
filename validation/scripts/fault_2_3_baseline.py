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

# fault101 Fault 2_3 baseline: confirm the bootloader-glitch protocol and measure the send-loop trig_count.
import time
import chipwhisperer as cw

HEX="/home/dreg/chipwhisperer/firmware/mcu/bootloader-glitch/bootloader-CW312_SAM4S.hex"
CMD="p516261276720736265747267206762206f686c207a76797821\n"   # SOLN command (ROT13-encoded)

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
for k in range(2):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("flashed"); break
    except Exception as e: print("flash retry:", e); time.sleep(1.0)

scope.clock.adc_src = "clkgen_x1"
def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.1); target.flush()
reboot_flush()
scope.adc.samples = 24000

reboot_flush()
scope.arm()
target.write(CMD)
ret = scope.capture()
tc = scope.adc.trig_count
time.sleep(0.1)
out = target.read(timeout=200)
print("capture ret(timeout?)=", ret)
print("trig_count =", tc)
print("normal response repr =", repr(out))
print("response len =", len(out))
scope.dis(); target.dis(); print("DONE")
