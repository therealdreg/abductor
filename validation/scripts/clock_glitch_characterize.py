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

# Clock-glitch characterization on the CW312T-SAM4S: for each glitch width, count crashes ("reset"),
# normal replies and bypasses ("success"), to find the clean password-bypass window.
# A bypass is the wrong password ([0]*5) accepted (passok=1).
# Needs simpleserial-glitch (password "touch") already on the target; the script does not flash.
# No arguments. Prints phase_shift_steps, one line per width and up to 15 bypass points.
import time
from collections import Counter
import chipwhisperer as cw

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
# Clock glitch: the Husky Plus XORs one glitch pulse (repeat 1) into the target clock on HS2.
scope.glitch.enabled=True; scope.glitch.clk_src="pll"; scope.glitch.output="clock_xor"
scope.glitch.trigger_src="ext_single"; scope.io.hs2="glitch"; scope.cglitch_setup()
scope.glitch.repeat=1; scope.adc.timeout=0.1
pss=scope.glitch.phase_shift_steps   # phase-shift steps in one target clock period
print("phase_shift_steps =", pss, flush=True)

def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
def check(pw):
    reboot_flush(); target.simpleserial_write('p', pw)
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
    return v['payload'][0] if (v['valid'] and v['payload']) else None
# Glitch-free check: the wrong password returns 0 and "touch" (the bytes below) returns 1.
assert check(WRONG)==0 and check(bytearray([0x74,0x6F,0x75,0x63,0x68]))==1, "sanity failed"
print("sanity OK", flush=True)

# One glitched attempt from a fresh reset: "success" is a bypass, "normal" a rejected password,
# "reset" a crash (capture timeout or no valid reply), after which the target is reset again.
def attempt(w,o,e):
    if scope.adc.state: reboot_flush()
    reboot_flush()
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    scope.arm(); target.simpleserial_write('p', WRONG)
    if scope.capture(): reboot_flush(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: reboot_flush(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

cw.set_all_log_levels(cw.logging.ERROR)
# 27 attempts per width: 3 offsets x 9 ext_offsets. Width and offset are Husky phase-shift steps;
# ext_offset is target clock cycles after the trigger.
WIDTHS=list(range(200, pss, 150))     # 200 up to phase_shift_steps, step 150
OFFS=[1200, 2000, 2800]
EXTS=list(range(50, 101, 6))           # 50 to 98, step 6: 9 values
succ_all=[]
for w in WIDTHS:
    c=Counter()
    for o in OFFS:
        for e in EXTS:
            cat=attempt(w,o,e); c[cat]+=1
            if cat=="success": succ_all.append((w,o,e))
    # tag a width with any bypass, or one with more crashes than normal replies
    tag = "  <-- SUCCESS" if c['success'] else ("  (crash zone)" if c['reset']>c['normal'] else "")
    print(f"width={w:4d}: reset={c['reset']:2d} normal={c['normal']:2d} success={c['success']:2d}{tag}", flush=True)
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()
print("SUCCESS params:", succ_all[:15])
print("DONE")
