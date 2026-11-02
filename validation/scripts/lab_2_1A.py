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

# sca101 Lab 2_1A, instruction power differences: checks whether captures through the Abductor are
# repeatable by measuring the execution cost (trigger duration) of instruction blocks inserted into
# simpleserial-base's get_pt().
# Target: CW312T-SAM4S with a ChipWhisperer Husky Plus. It sits in the straight board or the
# right-angle board (the Abductor variants, CW312-to-CW308 adapters on a CW308 UFO) or in the CW313.
# For each block in VARIANTS it patches a copy of simpleserial-base, builds it with the xpack ARM
# toolchain, flashes it over SAM-BA and captures 15 traces of 10000 samples. The trigger duration is
# scope.adc.trig_count, which counts ADC samples: 4 per core clock cycle at adc_mul=4.
# Set the hard-coded paths first. The script deletes and recreates simpleserial-base-lab2 in FWROOT.
# Argument: optional setup label such as ra or cw313. It only adds a subfolder, img/<label>, to the
# output path; the plot titles name the Abductor on every setup.
# Output: each block's trigger duration and cost against the baseline on the console, and
# 2_1A_cycles.png (bar chart) and 2_1A_traces.png (mean trace of each block).
import os, re, time, shutil, subprocess, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

PLATFORM = "CW312_SAM4S"
FWROOT   = "/home/dreg/chipwhisperer/firmware/mcu"
SRCBASE  = os.path.join(FWROOT, "simpleserial-base")
PRISTINE = os.path.join(SRCBASE, "simpleserial-base.c")
LABDIR   = os.path.join(FWROOT, "simpleserial-base-lab2")
HEX      = os.path.join(LABDIR, f"simpleserial-base-{PLATFORM}.hex")
CFILE    = os.path.join(LABDIR, "simpleserial-base.c")
TC       = "/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
OUT      = "/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); os.makedirs(OUT, exist_ok=True)
# Setup name for the plot titles, from the label: cw313, ra, or none for the straight board.
_LBL = sys.argv[1] if len(sys.argv) > 1 else ""
SETUP = ("on CW313" if "cw313" in _LBL else
         "via right-angle Abductor" if _LBL == "ra" or _LBL.startswith("ra_") or _LBL.endswith("_ra") else
         "via Abductor")
ENV      = dict(os.environ, PATH=TC + ":" + os.environ["PATH"])
SAMPLES  = 10000

# Instruction blocks inserted between trigger_high() and trigger_low(). Each name is the block's
# label in the console output and the plots. A and i are volatile, so every access is a real load
# or store. The divide label says multi-cycle, but for the constant 3 the compiler may emit a
# multiply-and-shift in place of SDIV, and the trigger duration cannot tell which.
VARIANTS = {
    "baseline (empty)": "",
    "20x A*=2 (unrolled mul)": "\n".join(["\tvolatile long int A = 0x2BAA;"] + ["\tA *= 2;"]*20),
    "loop x20 A*=2 (mul)": ("\tvolatile long int A = 0x2BAA;\n\tvolatile int i;\n"
                            "\tfor (i = 0; i < 20; i++) {\n\t\tA *= 2;\n\t}"),
    "loop x20 A/=3 (div, multi-cycle)": ("\tvolatile long int A = 0x2BAA;\n\tvolatile int i;\n"
                            "\tfor (i = 0; i < 20; i++) {\n\t\tA /= 3;\n\t}"),
}

def patch(code):
    # Read the unmodified simpleserial-base.c every time, so the blocks do not stack.
    src = open(PRISTINE).read()
    # Replace what lies between trigger_high(); and trigger_low(); with the block.
    src, n = re.subn(r"trigger_high\(\);.*?trigger_low\(\);",
                     "trigger_high();\n\n" + code + "\n\n\ttrigger_low();", src, flags=re.DOTALL)
    assert n == 1, f"trigger patch failed ({n})"
    # Remove the r reply (simpleserial_put), as the lab instructs, to leave an idle window after the
    # block. The z00 ack from simpleserial.c (SS_VER_1_1, the default) still follows: capture_trace
    # reads it in place of the r packet, warns "Unexpected start to command" and keeps the trace.
    src, n = re.subn(r"[ \t]*simpleserial_put\('r', 16, pt\);\n", "", src)
    assert n == 1, f"put removal failed ({n})"
    open(CFILE, "w").write(src)

def build():
    subprocess.run(["make", "clean"], cwd=LABDIR, env=ENV, capture_output=True)
    r = subprocess.run(["make", f"PLATFORM={PLATFORM}", "CRYPTO_TARGET=NONE", "-j"],
                       cwd=LABDIR, env=ENV, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(HEX):
        print(r.stdout[-1500:], r.stderr[-1500:]); raise RuntimeError("build failed")

# Capture n traces, all with the same key and plaintext. Returns the mean trace and the trigger
# duration of each capture, in ADC samples.
def capture_var(scope, target, n=15):
    ktp = cw.ktp.Basic(); key, text = ktp.next()
    ws=[]; tc=[]
    for _ in range(n):
        tr = cw.capture_trace(scope, target, text, key)
        if tr is None: continue
        ws.append(tr.wave); tc.append(int(scope.adc.trig_count))
    return np.mean(np.array(ws), axis=0), tc

print("=== connect ===")
scope = cw.scope(); target = cw.target(scope, cw.targets.SimpleSerial)
scope.default_setup(); scope.adc.samples = SAMPLES
# Patch a fresh copy, simpleserial-base-lab2, and leave simpleserial-base as it is.
if os.path.isdir(LABDIR): shutil.rmtree(LABDIR)
shutil.copytree(SRCBASE, LABDIR)

waves={}; trig={}
for name, code in VARIANTS.items():
    print(f"=== {name} ===")
    patch(code); build()
    cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX)
    # Pulse nRST low for 50 ms, release it and give the new firmware 200 ms to start.
    scope.io.nrst='low'; time.sleep(0.05); scope.io.nrst='high_z'; time.sleep(0.2)
    w, tc = capture_var(scope, target)
    waves[name]=w; trig[name]=int(round(np.median(tc)))
    print(f"   trigger duration = {trig[name]} ADC samples  (min={min(tc)} max={max(tc)}, {len(tc)} captures)")

scope.dis(); target.dis()
names=list(waves.keys())
cols=["#888888","#1f77b4","#2ca02c","#d62728"]

print("\n=== instruction block cost (trigger duration) ===")
base=trig[names[0]]
for nm in names:
    print(f"   {nm:34s}: {trig[nm]:5d} ADC samples  (+{trig[nm]-base:4d} vs baseline)")

# Figure 1, 2_1A_cycles.png: the median trigger duration of each block. The bars are in ADC samples
# (4 per core clock cycle), not cycles as the file name suggests.
plt.figure(figsize=(11,4.6))
bars=plt.bar(range(len(names)), [trig[nm] for nm in names], color=cols)
for b,nm in zip(bars,names):
    plt.text(b.get_x()+b.get_width()/2, b.get_height()+max(trig.values())*0.01,
             f"{trig[nm]} smp", ha="center", fontsize=9)
plt.xticks(range(len(names)), names, fontsize=8, rotation=8)
plt.ylabel("trigger duration (ADC samples, adc_mul=4)")
plt.title(f"sca101 Lab 2_1A: execution cost per instruction type\n(CW312T-SAM4S {SETUP} + Husky Plus)")
plt.grid(axis="y", alpha=0.3); plt.tight_layout()
plt.savefig(f"{OUT}/2_1A_cycles.png", dpi=115); plt.close()

# Figure 2, 2_1A_traces.png: the mean trace of each block, one panel per block, with a dashed line
# where the block ends.
fig, axs = plt.subplots(len(names), 1, figsize=(13, 8), sharex=True)
for ax, nm, col in zip(axs, names, cols):
    ax.plot(waves[nm], lw=0.4, color=col)
    end = trig[nm]   # trig_count counts ADC samples, the trace's x axis, so no adc_mul scaling
    if end <= SAMPLES:
        ax.axvline(end, color="k", ls="--", lw=0.9)
        ax.text(end+120, 0.08, f"block end\n{trig[nm]} smp", fontsize=7, va="center")
    ax.set_title(f"{nm}   ({trig[nm]} ADC samples)", fontsize=9, loc="left")
    ax.set_ylabel("power", fontsize=8); ax.grid(alpha=0.3)
axs[-1].set_xlabel("sample (adc_mul=4, 4 samples per clock cycle)")
fig.suptitle(f"sca101 Lab 2_1A: captured power traces per variant (CW312T-SAM4S {SETUP} + Husky Plus)", fontsize=11)
fig.tight_layout(rect=[0,0,1,0.98])
fig.savefig(f"{OUT}/2_1A_traces.png", dpi=115); plt.close()

print("\nsaved:", OUT+"/2_1A_cycles.png ,", OUT+"/2_1A_traces.png"); print("DONE")
