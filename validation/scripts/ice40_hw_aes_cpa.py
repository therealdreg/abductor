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

# CPA on the hardware AES of the CW312T-iCE40UP (iCE40UP5K FPGA). The FPGA runs an AES core that
# does one round per clock cycle, so it leaks on the last round: CPA with the last-round
# Hamming-distance model (round-9 to round-10 state register) recovers the round-10 key, and the
# inverse key schedule gives the master key. All 16 S-boxes switch in the same cycle, so each
# byte's SNR is far lower than in the SAM4S software AES and recovery needs thousands of traces,
# against about 30 for the SAM4S.
# Needs the CW312T-iCE40UP on the straight board, the right-angle board or the CW313. On the UFO,
# take the SAM4S debug wires off J8 first. The script loads the iCE40UP5K_SS2 AES bitstream (SS2
# wrapper) that ships with chipwhisperer and checks the known answer AES(0,0) before capturing.
# Usage: ice40_hw_aes_cpa.py [label] [ntraces]
#   label    default "abductor"; names the ChipWhisperer project PROJ, ice40_aes_<label>, which
#            each run overwrites
#   ntraces  random-plaintext traces with the fixed KEY, default 5000
# Prints the round-10 key, the master key and how many of its 16 bytes match KEY.
import sys, os, time
import numpy as np
import chipwhisperer as cw
import chipwhisperer.analyzer as cwa

LABEL = sys.argv[1] if len(sys.argv) > 1 else "abductor"
N     = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
KEY   = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
PROJ  = f"/tmp/claude-1000/-home-dreg-chipwhisperer/cd81b2e7-a660-4581-b013-a164a23eb746/scratchpad/ice40_aes_{LABEL}"

scope = cw.scope(); scope.default_setup(); scope.adc.samples = 1000
target = cw.target(scope, cw.targets.CW305, force=True, platform='ss2_ice40', program=True)
time.sleep(0.5)

# Known-answer test: AES with key 0 and plaintext 0 must give 66e94bd4...
tr = cw.capture_trace(scope, target, bytearray(16), bytearray(16), ack=False)
assert tr is not None and bytes(tr.textout).hex() == '66e94bd4ef8a2c3b884cfa59ca342b2e', "AES sanity failed"
print("AES sanity OK", flush=True)

proj = cw.create_project(PROJ, overwrite=True)
t0 = time.time()
for i in range(N):
    pt = bytearray(os.urandom(16))
    tr = cw.capture_trace(scope, target, pt, KEY, ack=False)
    if tr is not None:
        proj.traces.append(tr)
    if (i+1) % 1000 == 0:
        print(f"  captured {i+1}/{N}  ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
proj.save()
print(f"captured {len(proj.traces)} traces", flush=True)

leak_model = cwa.leakage_models.last_round_state_diff
attack = cwa.cpa(proj, leak_model)
results = attack.run()
lastkey = list(results.key_guess())
master  = cwa.aes_funcs.key_schedule_rounds(lastkey, 10, 0)
correct = sum(1 for a, b in zip(master, KEY) if a == b)
print("last-round key:", bytes(lastkey).hex(), flush=True)
print("master key    :", bytes(bytearray(master)).hex(), flush=True)
print("known key     :", bytes(KEY).hex(), flush=True)
print(f"CORRECT BYTES : {correct}/16   FULL KEY MATCH: {bytes(bytearray(master))==bytes(KEY)}", flush=True)
try: scope.dis()
except Exception: pass
try: target.dis()
except Exception: pass
print("DONE")
