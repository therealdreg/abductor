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

# Signal-integrity of the Abductor measurement path, two standard-methodology metrics on the SAM4S:
#   1) SNR  : chipwhisperer.analyzer calculate_snr with the SubBytes-output HW leakage model.
#   2) TVLA : non-specific fixed-vs-random Welch t-test (sca203 methodology), computed with numpy
#             (the cwtvla package is not installed; the Welch t-test formula is the same).
# A high SNR peak and a large |t| indicate the Abductor path resolves the AES leakage on this bench.
import os, time, subprocess, random
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw
import chipwhisperer.analyzer as cwa
from chipwhisperer.analyzer.attacks.snr import calculate_snr

OUT="/home/dreg/chipwhisperer/dregdoc/img"
import sys; LABEL=(sys.argv[1] if len(sys.argv)>1 else "abductor"); SUF=("" if LABEL=="abductor" else "_"+LABEL)
PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-aes"
HEX=f"{FWDIR}/simpleserial-aes-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])

if not os.path.exists(HEX):
    subprocess.run(["make",f"PLATFORM={PLATFORM}","CRYPTO_TARGET=TINYAES128C",f"SS_VER={SS_VER}","-j"],
                   cwd=FWDIR, env=ENV, capture_output=True)

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
for k in range(3):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("FLASHED", flush=True); break
    except Exception as e: print("flash retry", str(e)[:60], flush=True); time.sleep(1.0)
scope.adc.samples=3000
ktp=cw.ktp.Basic(); key,_=ktp.next(); target.set_key(key)

# ---------- 1) SNR (random plaintext, fixed key) ----------
N_SNR=1500
snr_traces=[]
for i in range(N_SNR):
    _,text=ktp.next()
    tr=cw.capture_trace(scope, target, text, key)
    if tr is not None: snr_traces.append(tr)
    if (i+1)%500==0: print(f"SNR capture {i+1}/{N_SNR}", flush=True)
# NOTE: calculate_snr(db=True) returns 20*ln(snr) (natural log), not standard dB. Use db=False to
# get the linear SNR (signal-variance / noise-variance) and convert to proper dB ourselves.
snr_lin=np.asarray(calculate_snr(snr_traces, cwa.leakage_models.sbox_output, bnum=0, db=False), dtype=float)
peak_lin=float(np.nanmax(snr_lin)); psamp=int(np.nanargmax(snr_lin)); peak_db=10*np.log10(peak_lin)
with np.errstate(divide='ignore',invalid='ignore'):
    snr_db=10*np.log10(np.where(snr_lin>0, snr_lin, np.nan))
print(f"SNR: peak linear = {peak_lin:.1f}  ( = {peak_db:.1f} dB )  at sample {psamp}  (byte0 SubBytes HW model, {len(snr_traces)} traces)", flush=True)

# ---------- 2) TVLA fixed-vs-random Welch t-test (fixed key) ----------
FIXED=bytearray.fromhex("da39a3ee5e6b4b0d3255bfef95601890")   # arbitrary fixed plaintext
N_TVLA=3000
A=[]; B=[]                                                    # A=fixed group, B=random group
for i in range(N_TVLA):
    if random.random()<0.5:
        tr=cw.capture_trace(scope, target, FIXED, key);  grp=A
    else:
        _,text=ktp.next(); tr=cw.capture_trace(scope, target, text, key); grp=B
    if tr is not None: grp.append(tr.wave)
    if (i+1)%1000==0: print(f"TVLA capture {i+1}/{N_TVLA}  (fixed={len(A)}, random={len(B)})", flush=True)
A=np.array(A); B=np.array(B)
tstat=(A.mean(0)-B.mean(0))/np.sqrt(A.var(0,ddof=1)/len(A)+B.var(0,ddof=1)/len(B))
maxt=float(np.nanmax(np.abs(tstat))); tsamp=int(np.nanargmax(np.abs(tstat)))
print(f"TVLA: max |t| = {maxt:.1f} at sample {tsamp}  (fixed n={len(A)}, random n={len(B)}; threshold 4.5)", flush=True)
print("=> leakage", "DETECTED (|t|>4.5) -> data-dependent leakage present in the measurement path" if maxt>4.5 else "not detected", flush=True)

scope.dis(); target.dis()

# ---------- plots ----------
fig,ax=plt.subplots(2,1,figsize=(11,7))
ax[0].plot(snr_db, color="#2171b5"); ax[0].axvline(psamp,color="r",ls="--",lw=1)
ax[0].set_title(f"SNR via Abductor (SubBytes byte0 HW model): peak linear {peak_lin:.1f} ({peak_db:.1f} dB) @ sample {psamp}")
ax[0].set_ylabel("SNR (dB, 10log10)"); ax[0].grid(alpha=0.3)
ax[1].plot(tstat, color="#08519c"); ax[1].axhline(4.5,color="r",ls="--",lw=1); ax[1].axhline(-4.5,color="r",ls="--",lw=1)
ax[1].set_title(f"TVLA fixed-vs-random Welch t-test via Abductor: max |t| = {maxt:.0f} (threshold 4.5)")
ax[1].set_xlabel("sample"); ax[1].set_ylabel("t-statistic"); ax[1].grid(alpha=0.3)
plt.suptitle(f"Signal integrity ({LABEL}): SNR + TVLA (CW312T-SAM4S, Husky Plus)")
plt.tight_layout(); plt.savefig(f"{OUT}/signal_integrity{SUF}.png", dpi=115); plt.close()
print("saved:", OUT+f"/signal_integrity{SUF}.png")
print("DONE")
