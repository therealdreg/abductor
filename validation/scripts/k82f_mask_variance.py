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

# Model-free detector of the LTC DPA mask. Capture many encryptions of one fixed plaintext+key.
#   mask OFF (constant seed): every encryption computes identical intermediate values -> traces
#                             differ chiefly by measurement noise -> low per-sample variance.
#   mask ON  (shipped, TRNG-reseeded): the internal masked values differ every time -> additional
#                             per-sample variance where the masked rounds compute.
# The excess variance of mask-ON over mask-OFF reflects the countermeasure's randomization,
# demonstrated without any key model. Usage: k82f_mask_variance.py <label>  [n_traces] [samples]
import sys, os, time
import numpy as np
import chipwhisperer as cw

LABEL   = sys.argv[1] if len(sys.argv) > 1 else "maskon"
N       = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
KEY = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
FIXED_PT = bytearray(range(16))
SCR = "/tmp/claude-1000/-home-dreg-chipwhisperer/cd81b2e7-a660-4581-b013-a164a23eb746/scratchpad"

scope = cw.scope(); scope.default_setup(); scope.adc.samples = SAMPLES
target = cw.target(scope, cw.targets.SimpleSerial2)
cw.set_all_log_levels(cw.logging.ERROR)
target.reset_comms(); target.set_key(KEY)
tr = cw.capture_trace(scope, target, FIXED_PT, KEY)
assert tr is not None and bytes(tr.textout).hex() == "50fe67cc996d32b6da0937e99bafec60", "KAT failed"
print(f"[{LABEL}] KAT OK; capturing {N} FIXED-input traces x {SAMPLES}", flush=True)

W=[]; t0=time.time()
for i in range(N):
    tr = cw.capture_trace(scope, target, FIXED_PT, KEY)   # same plaintext every time
    if tr is None: continue
    W.append(np.asarray(tr.wave, dtype=np.float32))
    if (i+1) % 1000 == 0: print(f"  {i+1}/{N}  ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
scope.dis(); target.dis()
T=np.array(W,dtype=np.float32); Nt=T.shape[0]
var = T.var(0)                      # per-sample variance over identical-input encryptions
np.save(f"{SCR}/k82f_var_{LABEL}.npy", var)
print(f"[{LABEL}] fixed-input per-sample variance: mean {var.mean():.3e}  "
      f"peak {var.max():.3e} @ sample {int(var.argmax())}  (n={Nt})", flush=True)
print("DONE")
