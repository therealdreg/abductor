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

# Signal/leakage metrics for the iCE40UP5K hardware AES via the Abductor:
#   (1) CPA convergence  - how many traces the last-round-HD CPA needs to recover the full key,
#   (2) TVLA             - non-specific fixed-vs-random Welch t-test (leakage detection).
# Both quantify the quality of the power measurement the Abductor delivers for a hardware (FPGA)
# target; the CPA in ice40_hw_aes_cpa.py already demonstrated full-key recovery, this quantifies it.
# Usage: ice40_sca_metrics.py [label] [n_cpa] [n_tvla]
import sys, os, time
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw
import chipwhisperer.analyzer as cwa

LABEL  = sys.argv[1] if len(sys.argv) > 1 else "abductor"
N_CPA  = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_TVLA = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
KEY    = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
OUT    = "/home/dreg/chipwhisperer/dregdoc/img" + (("/"+LABEL) if LABEL != "abductor" else "")
os.makedirs(OUT, exist_ok=True)

SBOX = np.array([
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16], dtype=np.uint8)
INV_SBOX = np.zeros(256, dtype=np.uint8)
for i, v in enumerate(SBOX): INV_SBOX[v] = i
HW = np.array([bin(x).count("1") for x in range(256)], dtype=np.float64)
INVSHIFT_undo = [0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11]      # CW LastroundStateDiff
# the last-round-HD CPA recovers the ROUND-10 key; map the known master key to it for scoring
K10 = list(cwa.aes_funcs.key_schedule_rounds(list(KEY), 0, 10))

scope = cw.scope(); scope.default_setup(); scope.adc.samples = 1000
target = cw.target(scope, cw.targets.CW305, force=True, platform='ss2_ice40', program=True)
time.sleep(0.5)
cw.set_all_log_levels(cw.logging.ERROR)
tr = cw.capture_trace(scope, target, bytearray(16), bytearray(16), ack=False)
assert tr is not None and bytes(tr.textout).hex() == '66e94bd4ef8a2c3b884cfa59ca342b2e', "AES sanity failed"
print("AES sanity OK; round-10 key (truth):", bytes(bytearray(K10)).hex(), flush=True)

def cap_batch(n, fixed_pt=None):
    """Capture n traces (fixed key). fixed_pt=None -> random plaintexts. Returns (waves, cts, pts)."""
    W = []; CT = []; PT = []; t0 = time.time()
    for i in range(n):
        pt = bytearray(fixed_pt) if fixed_pt is not None else bytearray(os.urandom(16))
        t = cw.capture_trace(scope, target, pt, KEY, ack=False)
        if t is None: continue
        W.append(t.wave); CT.append(list(bytes(t.textout))); PT.append(list(pt))
        if (i+1) % 1000 == 0: print(f"    {i+1}/{n}  ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
    return np.array(W), np.array(CT, dtype=np.uint8), np.array(PT, dtype=np.uint8)

# ---------- (1) CPA convergence (last-round HD model) ----------
print(f"=== capture {N_CPA} random-plaintext traces for CPA ===", flush=True)
Tc, CT, _ = cap_batch(N_CPA)
Nt = Tc.shape[0]
print(f"    captured {Nt} traces x {Tc.shape[1]} samples", flush=True)

def maxcorr_lastround(bnum, T, CT):
    """(256,) max |Pearson| over samples for each round-10 key guess at byte bnum."""
    g = np.arange(256, dtype=np.uint8)
    st10 = CT[:, INVSHIFT_undo[bnum]]                       # (n,) known ciphertext byte
    st9 = INV_SBOX[CT[:, bnum][None, :] ^ g[:, None]]       # (256, n) depends on guess
    H = HW[st9 ^ st10[None, :]]                             # (256, n) HD model
    Hc = H - H.mean(1, keepdims=True)
    Tcen = T - T.mean(0, keepdims=True)
    num = Hc @ Tcen
    den = np.sqrt((Hc**2).sum(1)[:, None] * (Tcen**2).sum(0)[None, :])
    return np.nan_to_num(np.abs(num/den)).max(axis=1)

print("=== CPA convergence: bytes-correct / PGE vs #traces ===", flush=True)
ns = [n for n in [50,100,200,400,700,1000,1500,2000,3000,4000,5000,6000] if n <= Nt] + [Nt]
ns = sorted(set(ns))
bytes_ok = []; pge = []
for n in ns:
    ranks = []
    for b in range(16):
        mc = maxcorr_lastround(b, Tc[:n], CT[:n])
        order = list(np.argsort(mc)[::-1])
        ranks.append(order.index(K10[b]))
    bytes_ok.append(sum(1 for r in ranks if r == 0))
    pge.append(float(np.mean(ranks)))
    print(f"    n={n:5d}  bytes_correct={bytes_ok[-1]:2d}/16  mean_PGE={pge[-1]:.2f}", flush=True)
solved = next((n for n, bo in zip(ns, bytes_ok) if bo == 16), None)
print(f"CPA full key ({16}/16) at {solved} traces", flush=True)

# ---------- (2) TVLA (fixed vs random, Welch t-test) ----------
print(f"=== capture {N_TVLA} interleaved fixed/random traces for TVLA ===", flush=True)
FIXED_PT = bytearray.fromhex("da39a3ee5e6b4b0d3255bfef95601890")   # arbitrary fixed TVLA vector
Wf = []; Wr = []; t0 = time.time()
for i in range(N_TVLA):
    use_fixed = (os.urandom(1)[0] & 1) == 0
    pt = FIXED_PT if use_fixed else bytearray(os.urandom(16))
    t = cw.capture_trace(scope, target, pt, KEY, ack=False)
    if t is None: continue
    (Wf if use_fixed else Wr).append(t.wave)
    if (i+1) % 1000 == 0: print(f"    {i+1}/{N_TVLA}  ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
A = np.array(Wf); B = np.array(Wr)
na, nb = A.shape[0], B.shape[0]
tval = (A.mean(0) - B.mean(0)) / np.sqrt(A.var(0, ddof=1)/na + B.var(0, ddof=1)/nb)
maxt = float(np.nanmax(np.abs(tval)))
print(f"TVLA: {na} fixed vs {nb} random; max |t| = {maxt:.1f}  "
      f"({'LEAKAGE (>4.5)' if maxt > 4.5 else 'no leakage'})", flush=True)

try: scope.dis()
except Exception: pass
try: target.dis()
except Exception: pass

# ---------- plots ----------
plt.figure(figsize=(11, 4.4))
plt.plot(ns, bytes_ok, 'o-', color="#1f77b4")
plt.axhline(16, color="green", ls="--", lw=0.8, label="full key (16/16)")
if solved: plt.axvline(solved, color="green", ls=":", lw=1.0, label=f"solved at {solved} traces")
plt.title(f"iCE40 hardware AES via {LABEL}: CPA convergence (last-round HD model)")
plt.xlabel("number of traces"); plt.ylabel("key bytes correct (of 16)")
plt.ylim(-0.5, 16.5); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
p1 = f"{OUT}/ice40_cpa_convergence.png"; plt.savefig(p1, dpi=115); plt.close()

plt.figure(figsize=(11, 4.4))
plt.plot(tval, color="#d62728", lw=0.7)
plt.axhline(4.5, color="k", ls="--", lw=0.8, label="+/-4.5 (TVLA threshold)")
plt.axhline(-4.5, color="k", ls="--", lw=0.8)
plt.title(f"iCE40 hardware AES via {LABEL}: TVLA fixed-vs-random t-test (max |t| = {maxt:.1f}, n={na}+{nb})")
plt.xlabel("sample"); plt.ylabel("Welch t-statistic"); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
p2 = f"{OUT}/ice40_tvla.png"; plt.savefig(p2, dpi=115); plt.close()

print(f"SUMMARY[{LABEL}]: CPA full key at {solved} traces; TVLA max|t|={maxt:.1f} (n={na}+{nb})", flush=True)
print("saved:", p1, ",", p2)
print("DONE")
