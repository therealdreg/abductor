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

# Comprehensive CPA battery on the K82F MMCAU hardware AES (via the Abductor). Captures once (cached)
# then tries several leakage models / POI techniques and reports how many key bytes each recovers:
#   A. blind full-window      - first-round HW, last-round HD, combined (no key used for selection)
#   B. profiled single-POI    - best known-key sample per byte, single-sample CPA
#   C. profiled matched filter- project each trace onto the byte's known-key correlation profile
#                               (linear combination of all leaky samples weighted by the profile) then
#                               CPA. This is a strong first-order technique; a byte it cannot recover
#                               shows no first-order leakage exploitable by this model on this bench.
# WARNING: methods B, C and D below are SELF-PROFILED (the POI / matched-filter profile is built from the
# KNOWN key on the same traces they are then scored on, with no disjoint train/test split), so they report
# an OPTIMISTIC, potentially false 16/16 and must NOT be read as a real key recovery. Only method A (blind,
# no key used for selection) and the disjoint-set attack in k82f_mf_rigor.py are trustworthy; the rigorous
# result is that the mmCAU is NOT broken by first-order CPA here (~1/16).
#   D. 32-bit word divide-and-conquer - the mmCAU works on 32-bit words, so single-byte leakage is
#                               diluted; using bytes already recovered, brute-force the remaining
#                               bytes of each word against a full-word Hamming-distance model.
# Usage: k82f_models.py [n_traces] [samples]
import sys, os, time
import numpy as np
import chipwhisperer.analyzer as cwa

N       = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
KEY = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
CACHE = "/tmp/claude-1000/-home-dreg-chipwhisperer/cd81b2e7-a660-4581-b013-a164a23eb746/scratchpad/k82f_mmcau50k"
SBOX = np.array([0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16], dtype=np.uint8)
INV_SBOX = np.zeros(256, np.uint8)
for i,v in enumerate(SBOX): INV_SBOX[v]=i
HW = np.array([bin(x).count("1") for x in range(256)], dtype=np.float32)
INVSHIFT_undo = [0,5,10,15,4,9,14,3,8,13,2,7,12,1,6,11]
K10 = list(cwa.aes_funcs.key_schedule_rounds(list(KEY),0,10))
g = np.arange(256, dtype=np.uint8)  # 0..255

# ---- capture (cached) ----
if os.path.exists(CACHE+"_T.npy") and np.load(CACHE+"_T.npy", mmap_mode="r").shape[0] >= N:
    T=np.load(CACHE+"_T.npy")[:N]; PT=np.load(CACHE+"_PT.npy")[:N]; CT=np.load(CACHE+"_CT.npy")[:N]
    print(f"loaded cache {T.shape}", flush=True)
else:
    import chipwhisperer as cw
    scope=cw.scope(); scope.default_setup(); scope.adc.samples=SAMPLES
    target=cw.target(scope, cw.targets.SimpleSerial2); cw.set_all_log_levels(cw.logging.ERROR)
    target.reset_comms(); target.set_key(KEY)
    tr=cw.capture_trace(scope,target,bytearray(range(16)),KEY)
    assert tr is not None and bytes(tr.textout).hex()=="50fe67cc996d32b6da0937e99bafec60","KAT failed"
    T=np.zeros((N,SAMPLES),np.float32); PT=np.zeros((N,16),np.uint8); CT=np.zeros((N,16),np.uint8)
    print(f"KAT OK; capturing {N}x{SAMPLES}", flush=True); k=0; t0=time.time()
    for i in range(N):
        pt=bytearray(os.urandom(16)); tr=cw.capture_trace(scope,target,pt,KEY)
        if tr is None: continue
        T[k]=tr.wave; PT[k]=list(pt); CT[k]=list(bytes(tr.textout)); k+=1
        if (i+1)%5000==0: print(f"  {i+1}/{N} ({(i+1)/(time.time()-t0):.0f}/s)", flush=True)
    scope.dis(); target.dis(); T=T[:k]; PT=PT[:k]; CT=CT[:k]
    np.save(CACHE+"_T.npy",T); np.save(CACHE+"_PT.npy",PT); np.save(CACHE+"_CT.npy",CT)
    print(f"captured+cached {k}", flush=True)
Nt=T.shape[0]
Tc=T-T.mean(0,keepdims=True); Tden=np.sqrt((Tc**2).sum(0)); Tden[Tden==0]=1
noise=1/np.sqrt(Nt)
print(f"N={Nt}, noise floor {noise:.4f}", flush=True)

def fr_hyp(b): return HW[SBOX[PT[:,b][None,:] ^ g[:,None]]]          # (256,N) first-round HW
def lr_hyp(b):
    st10=CT[:,INVSHIFT_undo[b]]; return HW[INV_SBOX[CT[:,b][None,:] ^ g[:,None]] ^ st10[None,:]]
def known(model,b): return (fr_hyp(b)[KEY[b]] if model=="fr" else lr_hyp(b)[K10[b]])
truth=lambda m,b:(KEY[b] if m=="fr" else K10[b])

def maxcorr_full(H):  # (256,) blind max over samples
    Hc=H-H.mean(1,keepdims=True)
    return np.nan_to_num(np.abs((Hc@Tc)/(np.sqrt((Hc**2).sum(1)[:,None]*(Tden**2)[None,:])))).max(1)
def ps(h):            # per-sample corr of a single hypothesis vector
    hc=h-h.mean(); return np.nan_to_num((hc@Tc)/(np.sqrt((hc**2).sum())*Tden))

def report(name, guesses):
    ok=[b for b in range(16) if guesses[b][0]==guesses[b][1]]
    print(f"  {name:34s}: {len(ok):2d}/16  bytes={sorted(ok)}", flush=True)
    return len(ok)

# A. blind full-window
for m,hyp in [("fr",fr_hyp),("lr",lr_hyp)]:
    report(f"A blind full-window {m}", [(int(maxcorr_full(hyp(b)).argmax()), truth(m,b)) for b in range(16)])
comb=[]
for b in range(16):
    gf=int(maxcorr_full(fr_hyp(b)).argmax()); gl=int(maxcorr_full(lr_hyp(b)).argmax())
    comb.append((0, 0 if (gf==KEY[b] or gl==K10[b]) else 1))
print(f"  A blind combined (fr OR lr)       : {sum(1 for c in comb if c[0]==c[1])}/16", flush=True)

# B/C. profiled single-POI and matched filter (per byte, best of fr/lr)
pB=[]; pC=[]
for b in range(16):
    best=None
    for m,hyp in [("fr",fr_hyp),("lr",lr_hyp)]:
        r=ps(known(m,b));
        if best is None or np.abs(r).max()>best[3]: best=(m,hyp,r,np.abs(r).max())
    m,hyp,r,_=best; s=int(np.abs(r).argmax())
    # single-POI CPA
    col=Tc[:,s]; cden=np.sqrt((col**2).sum()); H=hyp(b); Hc=H-H.mean(1,keepdims=True)
    gB=int(np.abs((Hc@col)/(np.sqrt((Hc**2).sum(1))*cden)).argmax())
    # matched filter: project traces onto the known-key correlation profile r
    mf=Tc@r; mden=np.sqrt((mf**2).sum()); gC=int(np.abs((Hc@mf)/(np.sqrt((Hc**2).sum(1))*mden)).argmax())
    pB.append((gB,truth(m,b))); pC.append((gC,truth(m,b)))
nB=report("B profiled single-POI", pB)
nC=report("C profiled matched-filter", pC)

# D. 32-bit word divide-and-conquer on the last round (state words = ShiftRow-undo columns)
# recovered set = bytes matched by C (matched filter); use them to peel words.
rec={b:pC[b][0] for b in range(16) if pC[b][0]==pC[b][1]}
k10rec=[rec.get(b) for b in range(16)]
WORDS=[[0,13,10,7],[4,1,14,11],[8,5,2,15],[12,9,6,3]]   # last-round diagonals (one mmCAU word each)
dc_ok=set(b for b in rec)
for w in WORDS:
    unknown=[b for b in w if k10rec[b] is None]; knownb=[b for b in w if k10rec[b] is not None]
    if not unknown or len(unknown)>2: continue         # brute-force <= 2^16
    # full-word last-round HD leak = sum of per-byte HD; correlate at each byte's own POI region
    base=np.zeros(Nt,np.float32)
    for b in knownb:
        st10=CT[:,INVSHIFT_undo[b]]; base+=HW[INV_SBOX[CT[:,b]^k10rec[b]]^st10]
    # matched filter over the word's samples (union of member POIs)
    prof=np.zeros(T.shape[1])
    for b in w: prof+=np.abs(ps(known("lr",b)))
    mf=Tc@prof; mden=np.sqrt((mf**2).sum())
    best=None
    import itertools
    for combo in itertools.product(range(256), repeat=len(unknown)):
        H=base.copy()
        for bi,kv in zip(unknown,combo):
            st10=CT[:,INVSHIFT_undo[bi]]; H=H+HW[INV_SBOX[CT[:,bi]^kv]^st10]
        Hc=H-H.mean(); c=abs((Hc@mf)/(np.sqrt((Hc**2).sum())*mden))
        if best is None or c>best[0]: best=(c,combo)
    for bi,kv in zip(unknown,best[1]):
        if kv==K10[bi]: dc_ok.add(bi)
print(f"  D 32-bit word divide-and-conquer  : {len(dc_ok)}/16  bytes={sorted(dc_ok)}", flush=True)
print(f"BEST: single-POI {nB}/16, matched-filter {nC}/16, word-D&C {len(dc_ok)}/16", flush=True)
print("DONE")
