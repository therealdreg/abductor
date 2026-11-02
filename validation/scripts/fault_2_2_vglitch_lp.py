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

# Low-power crowbar voltage glitch on the CW312T-SAM4S through the Abductor. The password-bypass
# demo (fault_2_2_vglitch_bypass.py) tests the high-power crowbar; this script uses the other
# crowbar MOSFET, scope.vglitch_setup('lp'), and sweeps scope.glitch.repeat over 1, 2, 4 and 8.
# Crashes that follow the repeat setting (a controlled fault) indicate that the low-power crowbar
# reaches the target through the Abductor VOUT node. Measured on all three setups: no crash at
# repeat 1 (0 of 18, too few to rule out a low rate) and a crash on every attempt at repeat 2, 4
# and 8. Both crowbars drive the same CROWBAR SMA, so this tests the same SMA and VOUT path as the
# high-power one, not the FILT_LP pin.
# Needs the prebuilt simpleserial-glitch hex in HEX, which the script flashes, and on the UFO the
# SMA tee at the UFO VOUT SMA. No arguments. Prints, for each repeat value, the crash percentage and
# the normal and bypass counts, and exits with status 2 if three flash tries fail.
import time
from collections import Counter
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"
HEX=f"/home/dreg/chipwhisperer/firmware/mcu/simpleserial-glitch/simpleserial-glitch-{PLATFORM}.hex"

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
ok=False
for k in range(3):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); ok=True; print("FLASHED", flush=True); break
    except Exception as e: print("flash retry", str(e)[:60], flush=True); time.sleep(1.0)
if not ok: print("FLASH FAILED - reconnect Husky USB", flush=True); raise SystemExit(2)

scope.vglitch_setup('lp', default_setup=False)            # low-power crowbar, same CROWBAR SMA
scope.glitch.trigger_src="ext_single"; scope.adc.timeout=0.1
target.reset_comms()

def rb(): scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.05); target.flush()
WRONG=bytearray([0]*5)
# Glitch-free check (the scope is not armed): the wrong password should return 0.
rb(); target.simpleserial_write('p', WRONG)
v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=1000)
print("sanity wrong-pw ->", v['payload'][0] if (v['valid'] and v['payload']) else None, flush=True)

# One glitched attempt: "success" is a bypass, "normal" a rejected password, "reset" a crash
# (capture timeout or no valid reply), after which the target is reset. A trigger still high
# (scope.adc.state) means the last attempt left the target hung.
def att(w,o,e,rep):
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e; scope.glitch.repeat=rep
    if scope.adc.state: rb()
    scope.arm(); target.simpleserial_write('p', WRONG); ret=scope.capture(); scope.io.vglitch_reset()
    if ret: rb(); return "reset"
    v=target.simpleserial_read_witherrors('r',1,glitch_timeout=10,timeout=50)
    if not v['valid'] or v['payload'] is None: rb(); return "reset"
    return "success" if v['payload'][0]==1 else "normal"

cw.set_all_log_levels(cw.logging.ERROR); rb()
# 18 attempts per repeat value: width 2000, offsets 2440, 2455 and 2470, ext_offset 126 to 136 in
# steps of 2. Width and offset are Husky phase-shift steps; ext_offset is target clock cycles after
# the trigger.
print("repeat | crash%  | normal | bypass   [width 2000, offset 2440/2455/2470, ext 126..136]", flush=True)
for rep in [1,2,4,8]:
    c=Counter()
    for o in [2440,2455,2470]:
        for e in range(126,137,2):
            c[att(2000,o,e,rep)]+=1
    n=sum(c.values())
    print("  %2d   | %5.1f%% | %6d | %d"%(rep, 100*c['reset']/n, c['normal'], c['success']), flush=True)
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()
print("Low-power crowbar exercised on the same CROWBAR SMA and VOUT path as the high-power one; "
      "the crash% table above shows this run's repeat threshold.", flush=True)
print("DONE")
