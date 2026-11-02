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

# Bring-up smoke test of the whole capture chain, from a ChipWhisperer Husky Plus to the
# CW312T-SAM4S. On the Abductor (CW312-to-CW308 adapter) the chain is Husky Plus, CW308 UFO,
# Abductor, target. It runs the same way on the straight board, the right-angle board and the CW313.
# It builds simpleserial-base (PLATFORM=CW312_SAM4S, SS_VER_1_1 by default) with the xpack ARM
# toolchain, flashes it over SAM-BA (exit status 2 if that fails), captures 10 traces with the p
# command and checks that each serial reply echoes the plaintext.
# Set FWDIR, TC and OUT for your machine first.
# Argument: optional setup label such as ra or cw313. It only adds a subfolder, img/<label>, to the
# output path, so move the target yourself. The plot title names the Abductor on every setup.
# Output: trace and echo counts plus trace statistics on the console, and the first 3 traces in
# 00_bringup_smoke_traces.png.
import logging, time, sys, os, subprocess
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import chipwhisperer as cw

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
PLATFORM = "CW312_SAM4S"
FWDIR = "/home/dreg/chipwhisperer/firmware/mcu/simpleserial-base"
HEX   = f"{FWDIR}/simpleserial-base-{PLATFORM}.hex"
TC    = "/home/dreg/toolchains/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
OUT   = "/home/dreg/chipwhisperer/dregdoc/img"+(("/"+sys.argv[1]) if len(sys.argv)>1 else ""); os.makedirs(OUT, exist_ok=True)
# Setup name for the plot titles, from the label: cw313, ra, or none for the straight board.
_LBL = sys.argv[1] if len(sys.argv) > 1 else ""
SETUP = ("on CW313" if "cw313" in _LBL else
         "via right-angle Abductor" if _LBL == "ra" or _LBL.startswith("ra_") or _LBL.endswith("_ra") else
         "via Abductor")
ENV   = dict(os.environ, PATH=TC + ":" + os.environ["PATH"])

print("=== 1) build simpleserial-base for the SAM4S ===")
subprocess.run(["make", f"PLATFORM={PLATFORM}", "CRYPTO_TARGET=NONE", "-j"], cwd=FWDIR, env=ENV, check=True)

print("=== 2) connect scope + target (SimpleSerial v1.1) ===")
scope = cw.scope(); target = cw.target(scope, cw.targets.SimpleSerial)
scope.default_setup()
print("clkgen_freq =", scope.clock.clkgen_freq, " adc_freq =", scope.clock.adc_freq, " adc_mul =", scope.clock.adc_mul)

print("=== 3) flash the SAM4S over SAM-BA (toggles ERASE (pdic) and nRST) ===")
t0 = time.time()
try:
    cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX)
    print("programming OK in %.1fs" % (time.time()-t0))
except Exception as e:
    print("!!! PROGRAMMING FAILED:", repr(e)); scope.dis(); target.dis(); sys.exit(2)

# Pulse nRST low for 50 ms, release it (high-Z) and give the new firmware 200 ms to start.
scope.io.nrst = 'low'; time.sleep(0.05); scope.io.nrst = 'high_z'; time.sleep(0.2)

print("=== 4) capture 10 traces + verify serial echo ===")
ktp = cw.ktp.Basic(); waves=[]; echo_ok=0; n=10
for i in range(n):
    key, text = ktp.next()
    tr = cw.capture_trace(scope, target, text, key)
    if tr is None:
        print(f"  trace {i}: None (no trigger)"); continue
    waves.append(tr.wave)
    # simpleserial-base sends the p plaintext back unchanged, so a match shows that TX and RX work.
    ok = tr.textout is not None and bytes(tr.textout) == bytes(text)
    echo_ok += int(ok)

print(f"RESULT: {len(waves)}/{n} traces captured, serial echo {echo_ok}/{n} correct")
if waves:
    W = np.array(waves)
    # mean p2p: per-trace peak-to-peak, averaged; global std: all samples. Normalized ADC units.
    print(f"  wave shape={W.shape}  mean p2p={np.ptp(W,axis=1).mean():.4f}  global std={W.std():.4f}")
    plt.figure(figsize=(12,4))
    for w in waves[:3]: plt.plot(w, lw=0.6)
    plt.title(f"Bring-up: CW312T-SAM4S {SETUP}, Husky Plus (simpleserial-base, p command)")
    plt.xlabel("sample"); plt.ylabel("power (normalized)"); plt.grid(alpha=0.3); plt.tight_layout()
    plt.savefig(f"{OUT}/00_bringup_smoke_traces.png", dpi=110)
    print("  saved:", OUT + "/00_bringup_smoke_traces.png")

scope.dis(); target.dis(); print("DONE")
