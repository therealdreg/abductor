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

# Non-specific TVLA (fixed-vs-random Welch t-test) on whatever K82F AES build is flashed, the
# unmasked mmCAU AES or one of the LTC mask builds: a blind leakage metric that needs no key model.
# Its max |t| compares the K82F hardware accelerator with the SAM4S software AES and the iCE40 FPGA
# AES, which get the same test.
# Flash the build with k82f_flash.sh first; the script checks the known answer before capturing.
# Usage: k82f_tvla.py [label] [n_traces] [samples]
#   label     default "k82f"; goes into the figure name and title
#   n_traces  default 8000, each one fixed or random by a coin flip
#   samples   samples per trace, default 5000
# Prints max |t| against the 4.5 threshold and saves
# /home/dreg/chipwhisperer/dregdoc/img/k82f_tvla_<label>.png. The title names the setup from the
# label: "cw313" in it gives the CW313, "ra" the right-angle board, anything else the straight board.
import sys, os, time
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

LABEL   = sys.argv[1] if len(sys.argv) > 1 else "k82f"
# Setup name for the plot titles, from the label: cw313, ra, or anything else for the straight board.
SETUP = ("on CW313" if "cw313" in LABEL else
         "via right-angle Abductor" if LABEL == "ra" or LABEL.startswith("ra_") or LABEL.endswith("_ra") else
         "via Abductor")
N       = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
KEY = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
FIXED_PT = bytearray.fromhex("da39a3ee5e6b4b0d3255bfef95601890")
OUT = "/home/dreg/chipwhisperer/dregdoc/img"

scope = cw.scope(); scope.default_setup(); scope.adc.samples = SAMPLES
target = cw.target(scope, cw.targets.SimpleSerial2)
cw.set_all_log_levels(cw.logging.ERROR)
target.reset_comms(); target.set_key(KEY)
tr = cw.capture_trace(scope, target, bytearray(range(16)), KEY)
assert tr is not None and bytes(tr.textout).hex() == "50fe67cc996d32b6da0937e99bafec60", "KAT failed"
print(f"[{LABEL}] KAT OK; TVLA capturing {N} traces x {SAMPLES} samples", flush=True)

# A holds the fixed-plaintext traces, B the random-plaintext ones.
A=[]; B=[]; t0=time.time()
for i in range(N):
    fixed = (os.urandom(1)[0] & 1) == 0
    pt = FIXED_PT if fixed else bytearray(os.urandom(16))
    tr = cw.capture_trace(scope, target, pt, KEY)
    if tr is None: continue
    (A if fixed else B).append(np.asarray(tr.wave, dtype=np.float32))
    if (i+1) % 2000 == 0: print(f"  {i+1}/{N}  ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
scope.dis(); target.dis()
A=np.array(A); B=np.array(B); na, nb = len(A), len(B)
tval = (A.mean(0) - B.mean(0)) / np.sqrt(A.var(0, ddof=1)/na + B.var(0, ddof=1)/nb)
maxt = float(np.nanmax(np.abs(tval)))
print(f"TVLA[{LABEL}]: {na} fixed vs {nb} random; max |t| = {maxt:.1f}  "
      f"({'LEAKAGE (>4.5)' if maxt>4.5 else 'no first-order leakage'})", flush=True)

plt.figure(figsize=(11,4.2))
plt.plot(tval, color="#d62728", lw=0.6)
plt.axhline(4.5, color="k", ls="--", lw=0.8, label="+/-4.5 threshold"); plt.axhline(-4.5, color="k", ls="--", lw=0.8)
plt.title(f"K82F {LABEL} {SETUP}: TVLA fixed-vs-random (max |t|={maxt:.1f}, n={na}+{nb})")
plt.xlabel("sample"); plt.ylabel("Welch t"); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
p=f"{OUT}/k82f_tvla_{LABEL}.png"; plt.savefig(p, dpi=115); plt.close()
print("saved:", p, flush=True); print("DONE")
