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

# Batch bypass rate of the high-power voltage-glitch password bypass. It flashes the prebuilt
# simpleserial-glitch hex for CW312_SAM4S, finds the best cell with a coarse search, then runs five
# 40-attempt batches there to give the rate and its spread between the batches of one run.
# Needs the SMA tee at the UFO VOUT SMA when the target is on the UFO.
# Usage: vglitch_rate_robust.py [label]   The label (default "abductor", for example "cw313") only
# tags the printout. Prints the best cell (as "optimum"), each batch and a ROBUST_RATE line with
# the mean and the range of the batch rates. Exits with status 2 if four flash tries fail.
import sys, time
import chipwhisperer as cw

LABEL = sys.argv[1] if len(sys.argv) > 1 else "abductor"
PLATFORM = "CW312_SAM4S"
HEX = f"/home/dreg/chipwhisperer/firmware/mcu/simpleserial-glitch/simpleserial-glitch-{PLATFORM}.hex"

scope = cw.scope(); target = cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
# Reset the SAM4S before flashing, so that program_target reaches SAM-BA even if an earlier test
# left the chip debug-halted or crashed.
scope.io.nrst = False; time.sleep(0.1); scope.io.nrst = "high_z"; time.sleep(0.3)
ok = False
for k in range(4):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); ok = True; print("FLASHED", flush=True); break
    except Exception as e: print("flash retry:", str(e)[:55], flush=True); time.sleep(1.0)
if not ok: print("FLASH FAILED - reconnect Husky USB", flush=True); raise SystemExit(2)

scope.vglitch_setup('hp', default_setup=False)
scope.glitch.trigger_src = "ext_single"; scope.adc.timeout = 0.1
target.reset_comms()
TOUCH = bytearray([0x74, 0x6F, 0x75, 0x63, 0x68]); WRONG = bytearray([0] * 5)

def rb(): scope.io.nrst = False; time.sleep(0.05); scope.io.nrst = "high_z"; time.sleep(0.05); target.flush()
def check(pw):
    rb(); target.simpleserial_write('p', pw)
    v = target.simpleserial_read_witherrors('r', 1, glitch_timeout=10, timeout=1000)
    return v['payload'][0] if (v['valid'] and v['payload']) else None
assert check(WRONG) == 0 and check(TOUCH) == 1, "firmware sanity failed"

# One glitched attempt: True for a bypass, False for a rejected password or a crash (capture timeout
# or no valid reply, after which the target is reset). A trigger still high (scope.adc.state) means
# the last attempt left the target hung.
def attempt(w, o, e):
    scope.glitch.width = w; scope.glitch.offset = o; scope.glitch.ext_offset = e
    if scope.adc.state: rb()
    scope.arm(); target.simpleserial_write('p', WRONG); ret = scope.capture(); scope.io.vglitch_reset()
    if ret: rb(); return False
    v = target.simpleserial_read_witherrors('r', 1, glitch_timeout=10, timeout=50)
    if not v['valid'] or v['payload'] is None: rb(); return False
    return v['payload'][0] == 1

cw.set_all_log_levels(cw.logging.ERROR); rb()
# Best cell: coarse search over 7 widths x 6 offsets (step 20) x 3 ext_offsets, 2 attempts per cell.
# Width and offset are Husky phase-shift steps; ext_offset is target clock cycles after the trigger.
# Ties keep the first cell found, so with no bypass at all the best cell is (1850, 2400, 128).
best = None; bestc = -1
for w in range(1850, 2151, 50):
    for o in range(2400, 2501, 20):
        for e in (128, 129, 130):
            c = sum(attempt(w, o, e) for _ in range(2))
            if c > bestc: bestc = c; best = (w, o, e)
print(f"optimum: {best}  ({bestc}/2 in search)", flush=True)

# Batch rate: 5 batches of 40 attempts at the best cell.
rates = []
for b in range(5):
    hits = sum(attempt(*best) for _ in range(40))
    rates.append(hits); print(f"batch {b+1}: {hits}/40 = {100*hits/40:.0f}%", flush=True)
cw.set_all_log_levels(cw.logging.WARNING)
mean = 100 * sum(rates) / (40 * len(rates))
print(f"ROBUST_RATE[{LABEL}]: optimum={best}, batches={rates}/40, "
      f"mean={mean:.1f}%  (range {100*min(rates)/40:.0f}-{100*max(rates)/40:.0f}%, n={40*len(rates)} shots)", flush=True)
scope.dis(); target.dis(); print("DONE")
