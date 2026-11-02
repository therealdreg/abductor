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

# Signal integrity of the measurement path: two standard leakage metrics on the CW312T-SAM4S with a
# ChipWhisperer Husky Plus, on the straight board, the right-angle board or the CW313. Both use a
# fixed key and 3000 samples per trace.
#   1) SNR: chipwhisperer.analyzer calculate_snr over 1500 random-plaintext traces, with the Hamming
#      weight of the SubBytes output of byte 0 as the leakage model.
#   2) TVLA: non-specific fixed-vs-random Welch t-test (sca203 method) over 3000 traces, computed
#      with numpy because the cwtvla package is not installed (same Welch t-test formula).
# A high SNR peak and a large |t| indicate that the path resolves the AES leak on this bench. |t|
# grows with the trace count, so compare setups only at equal counts.
# Needs simpleserial-aes (TINYAES128C, SS_VER_2_1) at HEX; the script builds it only if it is
# missing. Set the hard-coded paths first.
# Argument: optional setup label, default abductor (the straight board), shown in the main plot
# title. Any other label, such as ra or cw313, also goes into the figure name. The subplot titles
# name the Abductor on every setup.
# Output: the SNR peak (linear and dB) and max |t| with their samples on the console, and
# signal_integrity.png (signal_integrity_<label>.png for another label).
import os, time, subprocess, random
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw
import chipwhisperer.analyzer as cwa
from chipwhisperer.analyzer.attacks.snr import calculate_snr

OUT="/home/dreg/chipwhisperer/dregdoc/img"
import sys; LABEL=(sys.argv[1] if len(sys.argv)>1 else "abductor"); SUF=("" if LABEL=="abductor" else "_"+LABEL)
# Setup name for the plot titles, from the label: cw313, ra, or anything else for the straight board.
SETUP = ("on CW313" if "cw313" in LABEL else
         "via right-angle Abductor" if LABEL == "ra" or LABEL.startswith("ra_") or LABEL.endswith("_ra") else
         "via Abductor")
PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-aes"
HEX=f"{FWDIR}/simpleserial-aes-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])

# An existing hex is flashed as it is, whatever options built it, and the build result is not
# checked.
if not os.path.exists(HEX):
    subprocess.run(["make",f"PLATFORM={PLATFORM}","CRYPTO_TARGET=TINYAES128C",f"SS_VER={SS_VER}","-j"],
                   cwd=FWDIR, env=ENV, capture_output=True)

scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
# Up to 3 programming tries, 1 s apart; if all fail, the script stops with exit status 2.
for k in range(3):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("FLASHED", flush=True); break
    except Exception as e: print("flash retry", str(e)[:60], flush=True); time.sleep(1.0)
else:
    print("!!! SAM-BA programming failed after retries. Please reconnect the Husky USB.", flush=True); scope.dis(); target.dis(); raise SystemExit(2)
scope.adc.samples=3000
ktp=cw.ktp.Basic(); key,_=ktp.next(); target.set_key(key)

# 1) SNR: random plaintexts, fixed key.
N_SNR=1500
snr_traces=[]
for i in range(N_SNR):
    _,text=ktp.next()
    tr=cw.capture_trace(scope, target, text, key)
    if tr is not None: snr_traces.append(tr)
    if (i+1)%500==0: print(f"SNR capture {i+1}/{N_SNR}", flush=True)
# calculate_snr(db=True) returns 20*ln(snr), with the natural log, which is not standard dB. So ask
# for the linear SNR (signal variance over noise variance) with db=False and take 10*log10 here.
snr_lin=np.asarray(calculate_snr(snr_traces, cwa.leakage_models.sbox_output, bnum=0, db=False), dtype=float)
peak_lin=float(np.nanmax(snr_lin)); psamp=int(np.nanargmax(snr_lin)); peak_db=10*np.log10(peak_lin)
# SNR in dB for each sample, for the plot (NaN where the SNR is 0 or less)
with np.errstate(divide='ignore',invalid='ignore'):
    snr_db=10*np.log10(np.where(snr_lin>0, snr_lin, np.nan))
print(f"SNR: peak linear = {peak_lin:.1f}  ( = {peak_db:.1f} dB )  at sample {psamp}  (byte0 SubBytes HW model, {len(snr_traces)} traces)", flush=True)

# 2) TVLA fixed-vs-random Welch t-test, fixed key. A coin flip per trace picks the fixed plaintext
# or a random one, so each group gets about half of the 3000 traces.
FIXED=bytearray.fromhex("da39a3ee5e6b4b0d3255bfef95601890")   # arbitrary fixed plaintext
N_TVLA=3000
A=[]; B=[]                                                    # A: fixed-plaintext traces, B: random
for i in range(N_TVLA):
    if random.random()<0.5:
        tr=cw.capture_trace(scope, target, FIXED, key);  grp=A
    else:
        _,text=ktp.next(); tr=cw.capture_trace(scope, target, text, key); grp=B
    if tr is not None: grp.append(tr.wave)
    if (i+1)%1000==0: print(f"TVLA capture {i+1}/{N_TVLA}  (fixed={len(A)}, random={len(B)})", flush=True)
A=np.array(A); B=np.array(B)
# Welch's t for each sample: unequal variances, sample variances with ddof=1
tstat=(A.mean(0)-B.mean(0))/np.sqrt(A.var(0,ddof=1)/len(A)+B.var(0,ddof=1)/len(B))
maxt=float(np.nanmax(np.abs(tstat))); tsamp=int(np.nanargmax(np.abs(tstat)))
print(f"TVLA: max |t| = {maxt:.1f} at sample {tsamp}  (fixed n={len(A)}, random n={len(B)}; threshold 4.5)", flush=True)
print("=> leakage", "DETECTED (|t|>4.5) -> data-dependent leakage present in the measurement path" if maxt>4.5 else "not detected", flush=True)

scope.dis(); target.dis()

# Plots: SNR in dB (top), and the t statistic with threshold lines at 4.5 and -4.5 (bottom).
fig,ax=plt.subplots(2,1,figsize=(11,7))
ax[0].plot(snr_db, color="#2171b5"); ax[0].axvline(psamp,color="r",ls="--",lw=1)
ax[0].set_title(f"SNR {SETUP} (SubBytes byte0 HW model): peak linear {peak_lin:.1f} ({peak_db:.1f} dB) @ sample {psamp}")
ax[0].set_ylabel("SNR (dB, 10log10)"); ax[0].grid(alpha=0.3)
ax[1].plot(tstat, color="#08519c"); ax[1].axhline(4.5,color="r",ls="--",lw=1); ax[1].axhline(-4.5,color="r",ls="--",lw=1)
ax[1].set_title(f"TVLA fixed-vs-random Welch t-test {SETUP}: max |t| = {maxt:.0f} (threshold 4.5)")
ax[1].set_xlabel("sample"); ax[1].set_ylabel("t-statistic"); ax[1].grid(alpha=0.3)
plt.suptitle(f"Signal integrity ({LABEL}): SNR + TVLA (CW312T-SAM4S, Husky Plus)")
plt.tight_layout(); plt.savefig(f"{OUT}/signal_integrity{SUF}.png", dpi=115); plt.close()
print("saved:", OUT+f"/signal_integrity{SUF}.png")
print("DONE")
