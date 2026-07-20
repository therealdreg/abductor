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

# Bring-up smoke test: validate the full capture chain through the Abductor.
# Chain: ChipWhisperer Husky Plus -> CW308 UFO -> Abductor (CW312->CW308) -> CW312T-SAM4S.
# Builds simpleserial-base, flashes it over SAM-BA, then captures power traces and checks the serial echo.
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
ENV   = dict(os.environ, PATH=TC + ":" + os.environ["PATH"])

print("=== 1) build simpleserial-base for the SAM4S ===")
subprocess.run(["make", f"PLATFORM={PLATFORM}", "CRYPTO_TARGET=NONE", "-j"], cwd=FWDIR, env=ENV, check=True)

print("=== 2) connect scope + target (SimpleSerial v1.1) ===")
scope = cw.scope(); target = cw.target(scope, cw.targets.SimpleSerial)
scope.default_setup()
print("clkgen_freq =", scope.clock.clkgen_freq, " adc_freq =", scope.clock.adc_freq, " adc_mul =", scope.clock.adc_mul)

print("=== 3) flash the SAM4S over SAM-BA (toggles ERASE(pdic) + NRST through the Abductor) ===")
t0 = time.time()
try:
    cw.program_target(scope, cw.programmers.SAM4SProgrammer, HEX)
    print("programming OK in %.1fs" % (time.time()-t0))
except Exception as e:
    print("!!! PROGRAMMING FAILED:", repr(e)); scope.dis(); target.dis(); sys.exit(2)

scope.io.nrst = 'low'; time.sleep(0.05); scope.io.nrst = 'high_z'; time.sleep(0.2)

print("=== 4) capture 10 traces + verify serial echo ===")
ktp = cw.ktp.Basic(); waves=[]; echo_ok=0; n=10
for i in range(n):
    key, text = ktp.next()
    tr = cw.capture_trace(scope, target, text, key)
    if tr is None:
        print(f"  trace {i}: None (no trigger)"); continue
    waves.append(tr.wave)
    ok = tr.textout is not None and bytes(tr.textout) == bytes(text)
    echo_ok += int(ok)

print(f"RESULT: {len(waves)}/{n} traces captured, serial echo {echo_ok}/{n} correct")
if waves:
    W = np.array(waves)
    print(f"  wave shape={W.shape}  mean p2p={np.ptp(W,axis=1).mean():.4f}  global std={W.std():.4f}")
    plt.figure(figsize=(12,4))
    for w in waves[:3]: plt.plot(w, lw=0.6)
    plt.title("Bring-up: Abductor + CW312T-SAM4S via Husky Plus (simpleserial-base, p command)")
    plt.xlabel("sample"); plt.ylabel("power (normalized)"); plt.grid(alpha=0.3); plt.tight_layout()
    plt.savefig(f"{OUT}/00_bringup_smoke_traces.png", dpi=110)
    print("  saved:", OUT + "/00_bringup_smoke_traces.png")

scope.dis(); target.dis(); print("DONE")
