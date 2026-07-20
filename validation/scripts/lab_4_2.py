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

# sca101 Lab 4_2 - CPA on a Firmware AES Implementation (REAL HARDWARE)
# Target: CW312T-SAM4S on the Abductor (CW312->CW308) + CW308 UFO, ChipWhisperer Husky Plus.
# Correlation Power Analysis: model = HammingWeight(SBox(plaintext_byte XOR key_guess)); the key guess
# whose model correlates best (Pearson) with the traces is taken as the recovered key byte. Also plots key convergence (PGE).
import os, time, subprocess
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_2_1"; CRYPTO="TINYAES128C"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/simpleserial-aes"
HEX=f"{FWDIR}/simpleserial-aes-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
import sys, os as _os; OUT="/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); _os.makedirs(OUT, exist_ok=True)
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])
N=1000

SBOX=np.array([
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16], dtype=np.uint8)
HW=np.array([bin(x).count("1") for x in range(256)], dtype=np.float64)
SBOX_HW=HW[SBOX]  # HammingWeight(SBox[x])

print("=== build + flash simpleserial-aes ===")
subprocess.run(["make","clean"], cwd=FWDIR, env=ENV, capture_output=True)
r=subprocess.run(["make",f"PLATFORM={PLATFORM}",f"CRYPTO_TARGET={CRYPTO}",f"SS_VER={SS_VER}","-j"],
                 cwd=FWDIR, env=ENV, capture_output=True, text=True)
assert os.path.isfile(HEX), (r.stdout[-1500:]+r.stderr[-1500:])
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial2)
scope.default_setup()
for k in range(2):
    try: cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX); print("   flashed"); break
    except Exception as e: print("   flash retry:", e); time.sleep(1.0)

ktp=cw.ktp.Basic(); key,text=ktp.next(); known=list(bytes(key)); target.set_key(key)
print("known key:", "".join(f"{b:02x}" for b in known))
print(f"=== capture {N} AES traces ===")
t0=time.time(); traces=[]; textins=[]
for i in range(N):
    _, text = ktp.next()
    tr=cw.capture_trace(scope, target, text, key)
    if tr is None: continue
    traces.append(tr.wave); textins.append(list(bytes(tr.textin)))
scope.dis(); target.dis()
T=np.array(traces); PT=np.array(textins, dtype=np.uint8); Nt=T.shape[0]
print(f"   captured {Nt} traces of {T.shape[1]} samples in {time.time()-t0:.0f}s")

def cpa_maxcorr(byteidx, T, PT):
    """return (256,) max |Pearson corr| over samples for each key guess."""
    g=np.arange(256, dtype=np.uint8)
    H=SBOX_HW[PT[:,byteidx][None,:] ^ g[:,None]]        # (256, n) model
    Hc=H - H.mean(1, keepdims=True)
    Tc=T - T.mean(0, keepdims=True)
    num=Hc @ Tc                                          # (256, S)
    den=np.sqrt((Hc**2).sum(1)[:,None] * (Tc**2).sum(0)[None,:])
    corr=np.abs(num/den)
    return np.nan_to_num(corr).max(axis=1)

print("=== CPA: recover 16 key bytes ===")
recovered=[]; wcorr=[]; rcorr=[]
for b in range(16):
    mc=cpa_maxcorr(b, T, PT)
    order=np.argsort(mc)[::-1]
    recovered.append(int(order[0])); wcorr.append(float(mc[order[0]])); rcorr.append(float(mc[order[1]]))
    ok="OK" if recovered[b]==known[b] else "XX"
    print(f"   byte {b:2d}: {recovered[b]:02x} (known {known[b]:02x}) {ok}  corr={wcorr[b]:.3f} vs 2nd {rcorr[b]:.3f}")
match = recovered==known
print("RECOVERED:", "".join(f"{b:02x}" for b in recovered))
print("FULL KEY MATCH:", match)

print("=== convergence: PGE vs #traces ===")
ns=[5,10,15,20,30,40,60,80,120,160,220,300,500,Nt]
pge=[]
for n in ns:
    ranks=[]
    for b in range(16):
        mc=cpa_maxcorr(b, T[:n], PT[:n])
        order=list(np.argsort(mc)[::-1])
        ranks.append(order.index(known[b]))
    pge.append(np.mean(ranks))
    print(f"   n={n:4d}  mean PGE={pge[-1]:.2f}")
solved = next((n for n,p in zip(ns,pge) if p==0), None)

# figure 1: winner vs best-wrong correlation per byte
x=np.arange(16); w=0.4
plt.figure(figsize=(13,4.6))
plt.bar(x-w/2, wcorr, w, color="#2ca02c", label="correct key byte")
plt.bar(x+w/2, rcorr, w, color="#cccccc", label="best wrong guess")
plt.xticks(x, [f"{recovered[i]:02x}" for i in range(16)], fontsize=8)
plt.xlabel("key byte (recovered value)"); plt.ylabel("max |correlation|")
plt.title(f"sca101 Lab 4_2: {'FULL AES-128 KEY RECOVERED' if match else 'PARTIAL'} via CPA, {Nt} traces (CW312T-SAM4S via Abductor + Husky Plus)")
plt.legend(fontsize=8); plt.grid(axis="y", alpha=0.3); plt.tight_layout()
plt.savefig(f"{OUT}/4_2_cpa_result.png", dpi=115); plt.close()

# figure 2: key convergence (PGE vs traces)
plt.figure(figsize=(11,4.4))
plt.plot(ns, pge, 'o-', color="#1f77b4")
plt.axhline(0, color="green", ls="--", lw=0.8, label="full key found (PGE=0)")
if solved: plt.axvline(solved, color="green", ls=":", lw=1.0)
plt.title(f"sca101 Lab 4_2: key convergence, mean rank of correct key vs #traces (solved at {solved} traces)")
plt.xlabel("number of traces"); plt.ylabel("mean rank of correct subkey (over 16 bytes, single run)"); plt.legend(fontsize=8); plt.grid(alpha=0.3)
plt.tight_layout(); plt.savefig(f"{OUT}/4_2_cpa_convergence.png", dpi=115); plt.close()

print(f"solved (PGE=0) at {solved} traces")
print("saved:", OUT+"/4_2_cpa_result.png ,", OUT+"/4_2_cpa_convergence.png"); print("DONE")
