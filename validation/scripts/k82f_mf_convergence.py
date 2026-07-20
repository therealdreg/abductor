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

# =====================================================================================================
# WARNING: CIRCULAR / SELF-PROFILED COUNTER-EXAMPLE. NOT A VALID ATTACK, NOT A REAL KEY RECOVERY.
# The matched-filter profile is built from the KNOWN key on the first N traces and then scored on those
# SAME N traces (no disjoint profiling/attack split), so it overfits the noise and reports a false 16/16.
# It is kept only to illustrate why a disjoint train/test split is required. The trustworthy result is the
# disjoint-set attack in k82f_mf_rigor.py (recovers ~1/16; the mmCAU is NOT broken by first-order CPA here).
# =====================================================================================================
# Traces-to-key convergence for the profiled matched-filter CPA on the K82F MMCAU AES (offline,
# from the cached 50k traces). For each N: build the per-byte known-key correlation profile from the
# first N traces, project each trace onto it (matched filter combines the leaky samples weighted by
# that profile), then CPA. Reports bytes-correct vs N and saves the plot. No hardware.
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import chipwhisperer.analyzer as cwa
CACHE="/tmp/claude-1000/-home-dreg-chipwhisperer/cd81b2e7-a660-4581-b013-a164a23eb746/scratchpad/k82f_mmcau50k"
KEY=bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
SBOX=np.array([0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16],dtype=np.uint8)
INV_SBOX=np.zeros(256,np.uint8)
for i,v in enumerate(SBOX): INV_SBOX[v]=i
HW=np.array([bin(x).count("1") for x in range(256)],dtype=np.float32)
INVSHIFT_undo=[0,5,10,15,4,9,14,3,8,13,2,7,12,1,6,11]
K10=list(cwa.aes_funcs.key_schedule_rounds(list(KEY),0,10))
g=np.arange(256,dtype=np.uint8)
T=np.load(CACHE+"_T.npy"); PT=np.load(CACHE+"_PT.npy"); CT=np.load(CACHE+"_CT.npy"); Nmax=T.shape[0]
LABEL="abductor"

def fr_hyp(b,n): return HW[SBOX[PT[:n,b][None,:]^g[:,None]]]
def lr_hyp(b,n):
    st10=CT[:n,INVSHIFT_undo[b]]; return HW[INV_SBOX[CT[:n,b][None,:]^g[:,None]]^st10[None,:]]

def mf_bytes(n):
    Tc=T[:n]-T[:n].mean(0,keepdims=True); Tden=np.sqrt((Tc**2).sum(0)); Tden[Tden==0]=1
    ok=0
    for b in range(16):
        best=None
        for m,hyp,tv in [("fr",fr_hyp,KEY[b]),("lr",lr_hyp,K10[b])]:
            H=hyp(b,n); h=H[tv]; hc=h-h.mean()
            r=np.nan_to_num((hc@Tc)/(np.sqrt((hc**2).sum())*Tden))         # known-key profile
            mf=Tc@r; mden=np.sqrt((mf**2).sum()); Hc=H-H.mean(1,keepdims=True)
            corr=np.abs((Hc@mf)/(np.sqrt((Hc**2).sum(1))*mden))
            score=corr.max()
            if best is None or score>best[0]: best=(score,int(corr.argmax()),tv)
        if best[1]==best[2]: ok+=1
    return ok

ns=[n for n in [2000,5000,10000,15000,20000,30000,40000,50000] if n<=Nmax]; ns=sorted(set(ns))
conv=[]
for n in ns:
    conv.append(mf_bytes(n)); print(f"  n={n:6d}  matched-filter bytes_correct={conv[-1]:2d}/16", flush=True)
solved=next((n for n,c in zip(ns,conv) if c==16), None)
print(f"K82F MMCAU profiled matched-filter CPA: full key 16/16 at {solved} traces", flush=True)

plt.figure(figsize=(11,4.4))
plt.plot(ns, conv, 'o-', color="#8c564b", label="profiled matched-filter CPA")
plt.axhline(16, color="green", ls="--", lw=0.8, label="full key (16/16)")
if solved: plt.axvline(solved, color="green", ls=":", lw=1.0, label=f"solved at {solved} traces")
plt.axhline(4, color="#999999", ls="-.", lw=1.0, label="blind CPA best seen (4/16)")
plt.title(f"K82F MMCAU hardware AES via {LABEL}: CPA key recovery (blind fails, profiled recovers)")
plt.xlabel("number of traces"); plt.ylabel("key bytes correct (of 16)")
plt.ylim(-0.5,16.5); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
p="/home/dreg/chipwhisperer/dregdoc/img/k82f_mmcau_cpa_circular_mf.png"; plt.savefig(p,dpi=115); plt.close()
print("saved:",p,flush=True)
print("NOTE: this convergence is SELF-PROFILED (profile built and scored on the same traces) and is NOT a "
      "valid key recovery; see k82f_mf_rigor.py for the honest disjoint-set result.", flush=True)
print("DONE")
