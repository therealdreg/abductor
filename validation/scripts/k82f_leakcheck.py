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

# Leakage locator for the K82F MMCAU hardware AES (diagnostic). Uses the KNOWN key to compute the
# per-sample correlation of candidate leakage models: this is the "ideal CPA" and reports (a) whether
# these models leak in the captured window, (b) at which sample, (c) which model, and (d) an order-of-
# magnitude estimate of how many traces a blind CPA would need (n ~ 1/rho^2).
# Usage: k82f_leakcheck.py [n_traces] [samples] [offset]
import sys, os, time
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw
import chipwhisperer.analyzer as cwa

N       = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
OFFSET  = int(sys.argv[3]) if len(sys.argv) > 3 else 0
KEY = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
OUT = "/home/dreg/chipwhisperer/dregdoc/img"

SBOX = np.array([
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16], dtype=np.uint8)
INV_SBOX = np.zeros(256, dtype=np.uint8)
for i, v in enumerate(SBOX): INV_SBOX[v] = i
HW = np.array([bin(x).count("1") for x in range(256)], dtype=np.float64)
INVSHIFT_undo = [0,5,10,15,4,9,14,3,8,13,2,7,12,1,6,11]
K10 = list(cwa.aes_funcs.key_schedule_rounds(list(KEY), 0, 10))

scope = cw.scope(); scope.default_setup(); scope.adc.samples = SAMPLES
try: scope.adc.offset = OFFSET
except Exception: pass
target = cw.target(scope, cw.targets.SimpleSerial2)
cw.set_all_log_levels(cw.logging.ERROR)
target.reset_comms(); target.set_key(KEY)
W=[]; PTS=[]; CTS=[]; t0=time.time()
for i in range(N):
    pt = bytearray(os.urandom(16))
    tr = cw.capture_trace(scope, target, pt, KEY)
    if tr is None: continue
    W.append(tr.wave); PTS.append(list(pt)); CTS.append(list(bytes(tr.textout)))
scope.dis(); target.dis()
T=np.array(W); PT=np.array(PTS,dtype=np.uint8); CT=np.array(CTS,dtype=np.uint8); Nt=T.shape[0]
print(f"captured {Nt} traces x {SAMPLES} samples (offset {OFFSET})", flush=True)

# trace activity: where is the AES burst?
mstd = T.std(0)
print(f"trace std: peak {mstd.max():.4f} at sample {int(mstd.argmax())}; median {np.median(mstd):.4f}", flush=True)

def persample_corr(H1d, T):
    """H1d: (n,) model for the CORRECT key -> (S,) Pearson corr per sample."""
    Hc = H1d - H1d.mean()
    Tc = T - T.mean(0, keepdims=True)
    num = Hc @ Tc
    den = np.sqrt((Hc**2).sum() * (Tc**2).sum(0))
    return np.nan_to_num(num/den)

print("=== known-key leakage per byte (peak |corr| and location) ===", flush=True)
def fr_model(b): return HW[SBOX[PT[:, b] ^ KEY[b]]]
def lr_model(b): return HW[INV_SBOX[CT[:, b] ^ K10[b]] ^ CT[:, INVSHIFT_undo[b]]]
best = {"first-round HW": (0,0,0), "last-round HD": (0,0,0)}
agg_fr = np.zeros(T.shape[1]); agg_lr = np.zeros(T.shape[1])
for b in range(16):
    cfr = np.abs(persample_corr(fr_model(b), T)); agg_fr += cfr
    clr = np.abs(persample_corr(lr_model(b), T)); agg_lr += clr
    if cfr.max() > best["first-round HW"][0]: best["first-round HW"] = (cfr.max(), b, int(cfr.argmax()))
    if clr.max() > best["last-round HD"][0]: best["last-round HD"] = (clr.max(), b, int(clr.argmax()))
    if b < 4:
        print(f"  byte {b}: first-round |rho|={cfr.max():.3f}@{int(cfr.argmax())}   "
              f"last-round |rho|={clr.max():.3f}@{int(clr.argmax())}", flush=True)
for name,(rho,b,s) in best.items():
    need = int(28/(rho**2)) if rho>0.005 else None
    print(f"BEST {name:16s}: |rho|={rho:.3f} (byte {b}, sample {s}) -> ~{need} traces to break" if need
          else f"BEST {name:16s}: |rho|={rho:.3f} (no measurable leakage under these models)", flush=True)

plt.figure(figsize=(12,5))
plt.subplot(2,1,1); plt.plot(T.mean(0), lw=0.5); plt.plot(mstd, lw=0.5, alpha=0.7)
plt.title(f"K82F MMCAU: mean trace + std ({Nt} traces, {SAMPLES} samples, offset {OFFSET})"); plt.grid(alpha=0.3)
plt.subplot(2,1,2); plt.plot(agg_fr, lw=0.6, label="first-round HW (sum |rho| over 16 bytes)")
plt.plot(agg_lr, lw=0.6, label="last-round HD (sum |rho|)")
plt.xlabel("sample"); plt.ylabel("sum |corr|, known key"); plt.legend(fontsize=8); plt.grid(alpha=0.3)
plt.tight_layout(); p=f"{OUT}/k82f_leakcheck.png"; plt.savefig(p, dpi=110); plt.close()
print("saved:", p, flush=True); print("DONE")
