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

# Control experiment: is the K82F MMCAU's CPA resistance a property of the TARGET or an artifact of the
# Abductor? Capture a matched 50k set on the CW313-native baseboard and run the same analysis as on the
# Abductor, side by side. If both setups leak comparably (byte-0 |rho|, count of leaky bytes, and
# blind/rigorous byte counts matching within run-to-run variance), the resistance points to the target
# rather than the adapter.
# Run with the K82F (MMCAU) on the CW313. Usage: k82f_compare.py [n_traces] [samples]
import sys, os, time
import numpy as np
import chipwhisperer.analyzer as cwa
N       = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
KEY=bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
SCR="/tmp/claude-1000/-home-dreg-chipwhisperer/cd81b2e7-a660-4581-b013-a164a23eb746/scratchpad"
ABD=f"{SCR}/k82f_mmcau50k"; CW3=f"{SCR}/k82f_mmcau50k_cw313"
SBOX=np.array([0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16],dtype=np.uint8)
INV_SBOX=np.zeros(256,np.uint8)
for i,v in enumerate(SBOX): INV_SBOX[v]=i
HW=np.array([bin(x).count("1") for x in range(256)],dtype=np.float32)
INVSHIFT_undo=[0,5,10,15,4,9,14,3,8,13,2,7,12,1,6,11]
K10=list(cwa.aes_funcs.key_schedule_rounds(list(KEY),0,10))
g=np.arange(256,dtype=np.uint8)

# ---- capture CW313 if not cached ----
if not (os.path.exists(CW3+"_T.npy") and np.load(CW3+"_T.npy",mmap_mode="r").shape[0]>=N):
    import chipwhisperer as cw
    scope=cw.scope(); scope.default_setup(); scope.adc.samples=SAMPLES
    target=cw.target(scope,cw.targets.SimpleSerial2); cw.set_all_log_levels(cw.logging.ERROR)
    target.reset_comms(); target.set_key(KEY)
    tr=cw.capture_trace(scope,target,bytearray(range(16)),KEY)
    assert tr is not None and bytes(tr.textout).hex()=="50fe67cc996d32b6da0937e99bafec60","KAT failed"
    T=np.zeros((N,SAMPLES),np.float32); PT=np.zeros((N,16),np.uint8); CT=np.zeros((N,16),np.uint8)
    print(f"[CW313] KAT OK; capturing {N}x{SAMPLES}",flush=True); k=0; t0=time.time()
    for i in range(N):
        pt=bytearray(os.urandom(16)); tr=cw.capture_trace(scope,target,pt,KEY)
        if tr is None: continue
        T[k]=tr.wave; PT[k]=list(pt); CT[k]=list(bytes(tr.textout)); k+=1
        if (i+1)%5000==0: print(f"  {i+1}/{N} ({(i+1)/(time.time()-t0):.0f}/s)",flush=True)
    scope.dis(); target.dis(); T=T[:k];PT=PT[:k];CT=CT[:k]
    np.save(CW3+"_T.npy",T); np.save(CW3+"_PT.npy",PT); np.save(CW3+"_CT.npy",CT)
    print(f"[CW313] captured+cached {k}",flush=True)

def analyze(base, name):
    T=np.load(base+"_T.npy"); PT=np.load(base+"_PT.npy"); CT=np.load(base+"_CT.npy"); Nt=T.shape[0]
    Tc=T-T.mean(0,keepdims=True); Tden=np.sqrt((Tc**2).sum(0)); Tden[Tden==0]=1; noise=1/np.sqrt(Nt)
    # per-byte known-key leakage: best model, peak |rho|, #significant POIs
    peak=[]; npoi=[]; models=[]
    for b in range(16):
        best=None
        for m,tv in [("fr",KEY[b]),("lr",K10[b])]:
            if m=="fr": h=HW[SBOX[PT[:,b]^tv]]
            else:       h=HW[INV_SBOX[CT[:,b]^tv]^CT[:,INVSHIFT_undo[b]]]
            hc=h-h.mean(); r=np.nan_to_num((hc@Tc)/(np.sqrt((hc**2).sum())*Tden))
            if best is None or np.abs(r).max()>best[1]: best=(m,np.abs(r).max(),int((np.abs(r)>5*noise).sum()))
        models.append(best[0]); peak.append(best[1]); npoi.append(best[2])
    # blind full-window combined bytes
    def blind(b):
        gf=int(np.nan_to_num(np.abs(((HW[SBOX[PT[:,b][None,:]^g[:,None]]]-HW[SBOX[PT[:,b][None,:]^g[:,None]]].mean(1,keepdims=True))@Tc)/(np.sqrt((( HW[SBOX[PT[:,b][None,:]^g[:,None]]]-HW[SBOX[PT[:,b][None,:]^g[:,None]]].mean(1,keepdims=True))**2).sum(1)[:,None]*(Tden**2)[None,:])))).max(1).argmax())
        st10=CT[:,INVSHIFT_undo[b]]; Hl=HW[INV_SBOX[CT[:,b][None,:]^g[:,None]]^st10[None,:]]; Hlc=Hl-Hl.mean(1,keepdims=True)
        gl=int(np.nan_to_num(np.abs((Hlc@Tc)/(np.sqrt((Hlc**2).sum(1)[:,None]*(Tden**2)[None,:])))).max(1).argmax())
        return gf==KEY[b] or gl==K10[b]
    nblind=sum(1 for b in range(16) if blind(b))
    # rigorous disjoint profiled (POI-thresholded, single best POI transferred)
    P=Nt//2; Tp=T[:P];PTp=PT[:P];CTp=CT[:P]; Ta=T[P:];PTa=PT[P:];CTa=CT[P:]
    Tpc=Tp-Tp.mean(0,keepdims=True); Tpden=np.sqrt((Tpc**2).sum(0)); Tpden[Tpden==0]=1; pn=1/np.sqrt(P)
    Tac=Ta-Ta.mean(0,keepdims=True); Tad=np.sqrt((Tac**2).sum(0)); Tad[Tad==0]=1
    nrig=0
    for b in range(16):
        best=None
        for m,tv in [("fr",KEY[b]),("lr",K10[b])]:
            if m=="fr": h=HW[SBOX[PTp[:,b]^tv]]
            else:       h=HW[INV_SBOX[CTp[:,b]^tv]^CTp[:,INVSHIFT_undo[b]]]
            hc=h-h.mean(); r=np.nan_to_num((hc@Tpc)/(np.sqrt((hc**2).sum())*Tpden))
            if best is None or np.abs(r).max()>best[2]: best=(m,int(np.abs(r).argmax()),np.abs(r).max())
        m,s,_=best
        if m=="fr": H=HW[SBOX[PTa[:,b][None,:]^g[:,None]]]; truth=KEY[b]
        else:       H=HW[INV_SBOX[CTa[:,b][None,:]^g[:,None]]^CTa[:,INVSHIFT_undo[b]][None,:]]; truth=K10[b]
        Hc=H-H.mean(1,keepdims=True); col=Tac[:,s]; cden=Tad[s]
        if int(np.abs((Hc@col)/(np.sqrt((Hc**2).sum(1))*cden)).argmax())==truth: nrig+=1
    return dict(name=name,Nt=Nt,noise=noise,peak=peak,npoi=npoi,models=models,nblind=nblind,nrig=nrig,
                tracestd=float(np.median(np.sqrt(Tden**2/Nt))))

A=analyze(ABD,"Abductor"); C=analyze(CW3,"CW313")
print("\n================ K82F MMCAU: Abductor vs CW313 (same target, same settings) ================",flush=True)
print(f"{'byte':>4} | {'Abductor |rho| (POIs)':>24} | {'CW313 |rho| (POIs)':>22} | model", flush=True)
for b in range(16):
    print(f"{b:>4} | {A['peak'][b]:>10.3f} ({A['npoi'][b]:>4})        | {C['peak'][b]:>10.3f} ({C['npoi'][b]:>4})      | {A['models'][b]}/{C['models'][b]}", flush=True)
print("-"*90, flush=True)
print(f"byte-0 |rho|:            Abductor {A['peak'][0]:.3f}   CW313 {C['peak'][0]:.3f}", flush=True)
print(f"bytes with any sig. POI: Abductor {sum(1 for x in A['npoi'] if x>0)}/16   CW313 {sum(1 for x in C['npoi'] if x>0)}/16", flush=True)
print(f"blind full-window bytes: Abductor {A['nblind']}/16   CW313 {C['nblind']}/16", flush=True)
print(f"rigorous disjoint bytes: Abductor {A['nrig']}/16   CW313 {C['nrig']}/16", flush=True)
print(f"median trace noise:      Abductor {A['tracestd']:.4e}   CW313 {C['tracestd']:.4e}", flush=True)
print("\nVERDICT:", "TARGET (both setups resist CPA equivalently on this run)" if abs(A['peak'][0]-C['peak'][0])<0.04 and abs(A['nrig']-C['nrig'])<=2
      else "DIFFERENT -> investigate adapter", flush=True)
print("DONE")
