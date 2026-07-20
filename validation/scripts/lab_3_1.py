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

# sca101 Lab 3_1 - Large Hamming Weight Swings
# Target: CW312T-SAM4S on the Abductor (CW312->CW308) + CW308 UFO, ChipWhisperer Husky Plus.
# Shows the target's power depends on the data it manipulates: force plaintext byte 0 to 0x00 (HW 0)
# or 0xFF (HW 8), run AES, then the difference of the two group means shows a data-dependent spike.
import os, time, subprocess
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"; CRYPTO="TINYAES128C"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-aes"
HEX=f"{FWDIR}/simpleserial-aes-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
import sys; OUT="/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); os.makedirs(OUT, exist_ok=True)
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])
N=200

print("=== build simpleserial-aes (TINYAES128C) ===")
subprocess.run(["make","clean"], cwd=FWDIR, env=ENV, capture_output=True)
r=subprocess.run(["make",f"PLATFORM={PLATFORM}",f"CRYPTO_TARGET={CRYPTO}",f"SS_VER={SS_VER}","-j"],
                 cwd=FWDIR, env=ENV, capture_output=True, text=True)
assert os.path.isfile(HEX), (r.stdout[-1800:]+r.stderr[-1800:])
print("   built", os.path.basename(HEX))

print("=== connect + program ===")
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()

def program_with_retry(tries=2):
    for k in range(tries):
        try:
            cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX)
            print(f"   programmed OK (attempt {k+1})"); return True
        except Exception as e:
            print(f"   programming attempt {k+1} failed: {e}"); time.sleep(1.0)
    return False

if not program_with_retry():
    print("!!! SAM-BA programming failed after retries. Please reconnect the Husky USB."); scope.dis(); target.dis(); raise SystemExit(2)

ktp=cw.ktp.Basic()
key, text = ktp.next()
target.set_key(key)

print(f"=== capture {N} traces (plaintext byte0 forced to 0x00 or 0xFF) ===")
traces=[]; b0=[]
for i in range(N):
    _, text = ktp.next()
    text[0] = 0xFF if (text[0] & 0x01) else 0x00
    tr = cw.capture_trace(scope, target, text, key)
    if tr is None:
        continue
    traces.append(tr.wave); b0.append(int(text[0]))
traces=np.array(traces); b0=np.array(b0)
one = traces[b0==0xFF]; zero = traces[b0==0x00]
print(f"   captured {len(traces)}  (0xFF: {len(one)}, 0x00: {len(zero)})")

one_avg=one.mean(axis=0); zero_avg=zero.mean(axis=0)
diff = one_avg - zero_avg
loc=int(np.argmax(np.abs(diff))); peak=float(diff[loc])
# noise floor: std of diff on a quiet window far from the peak
quiet = np.concatenate([diff[:max(0,loc-400)], diff[min(len(diff),loc+400):]])
noise=float(np.std(quiet))
print(f"=== result: peak |diff|={abs(peak):.4f} at sample {loc}, noise std={noise:.4f}, peak/noise-std x{abs(peak)/noise:.1f} (informal ratio, not an SNR) ===")

# figure 1: difference of group means (Hamming-weight leak)
plt.figure(figsize=(13,4.2))
plt.plot(diff, lw=0.7, color="#1f77b4")
plt.plot(loc, peak, 'rv', ms=9)
plt.annotate(f"leak spike\nsample {loc}, |diff|={abs(peak):.3f}", (loc,peak),
             textcoords="offset points", xytext=(20,-10 if peak>0 else 10), fontsize=8, color="red")
plt.title("sca101 Lab 3_1: difference of means, plaintext byte0 = 0xFF minus 0x00 (CW312T-SAM4S via Abductor + Husky Plus)")
plt.xlabel("sample"); plt.ylabel("mean power difference"); plt.grid(alpha=0.3); plt.tight_layout()
plt.savefig(f"{OUT}/3_1_diff.png", dpi=115); plt.close()

# figure 2: the two group means overlaid, zoomed on the leak
a=max(0,loc-150); z=min(len(diff),loc+150)
plt.figure(figsize=(13,4.2))
plt.plot(range(a,z), zero_avg[a:z], lw=1.0, label="byte0 = 0x00 (HW 0)")
plt.plot(range(a,z), one_avg[a:z],  lw=1.0, label="byte0 = 0xFF (HW 8)")
plt.axvline(loc, color="k", ls="--", lw=0.8)
plt.title("sca101 Lab 3_1: group-mean power around the leak sample (CW312T-SAM4S via Abductor + Husky Plus)")
plt.xlabel("sample"); plt.ylabel("mean power"); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
plt.savefig(f"{OUT}/3_1_groups_zoom.png", dpi=115); plt.close()

scope.dis(); target.dis()
print("saved:", OUT+"/3_1_diff.png ,", OUT+"/3_1_groups_zoom.png"); print("DONE")
