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

# Standardized voltage-glitch benchmark for comparing bench configurations (T quality, CW313, ...).
# Same sweep + same peak-rate measurement each run, so the numbers are comparable across runs.
# Usage: python vglitch_benchmark.py "<config label>"
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
def attempt(w,o,e):
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    if scope.adc.state: reboot_flush()
    scope.arm(); target.simpleserial_write('p', WRONG); ret=scope.capture(); scope.io.vglitch_reset()
    if ret: reboot_flush(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: reboot_flush(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

assert check(WRONG)==0 and check(bytearray([0x74,0x6F,0x75,0x63,0x68]))==1, "firmware sanity failed"
cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()

# --- fixed locate sweep (grid held constant across configs) ---
WIDTHS=list(range(1500,2301,50)); OFFS=list(range(2440,2501,10)); EXTS=list(range(126,133))
cnt=Counter(); cellsucc=Counter()
for w in WIDTHS:
    for o in OFFS:
        for e in EXTS:
            c=attempt(w,o,e); cnt[c]+=1
            if c=="success": cellsucc[(w,o,e)]+=1
sweep_att=sum(cnt.values()); sweep_succ=cnt["success"]
best=max(cellsucc, key=cellsucc.get) if cellsucc else (2020,2490,129)

# --- fixed peak-rate measurement at best cell ---
REPS=40; hit=sum(1 for _ in range(REPS) if attempt(*best)=="success")
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()

print(f"BENCHMARK[{LABEL}]: sweep_yield={sweep_succ}/{sweep_att} ({100*sweep_succ/sweep_att:.2f}%), "
      f"resets={cnt['reset']}/{sweep_att} ({100*cnt['reset']/sweep_att:.1f}%), "
      f"best={best}, peak_rate={hit}/{REPS} ({100*hit/REPS:.0f}%)")
print("DONE")
