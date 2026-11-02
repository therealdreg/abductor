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

# CW312T-K82F bring-up: a known-answer test through the Abductor. Flash the firmware with
# k82f_flash.sh first. One encryption checks that the Husky Plus reaches the K82F: the serial
# (LPUART), the clock (HS2, 7.37 MHz), the trigger and the firmware's hardware AES. The other K82F
# capture scripts, except k82f_leakcheck.py, assert the same known answer:
# AES(key=2b7e.., pt=00..0f) = 50fe67cc996d32b6da0937e99bafec60.
# No arguments. Prints the clock setup, the ciphertext next to the expected one and the number of
# samples captured, then DONE or FAILED. Exits with status 2 if the K82F gives no answer in 4 tries.
import sys, time
import chipwhisperer as cw

KEY = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
PT  = bytearray(range(16))
EXPECT = "50fe67cc996d32b6da0937e99bafec60"

scope = cw.scope(); scope.default_setup()
scope.adc.samples = 5000
target = cw.target(scope, cw.targets.SimpleSerial2)
print(f"clkgen={scope.clock.clkgen_freq/1e6:.2f} MHz  hs2={scope.io.hs2}  adc_freq={scope.clock.adc_freq/1e6:.2f} MHz", flush=True)

target.reset_comms()
target.set_key(KEY)
ct = None
for attempt in range(4):
    tr = cw.capture_trace(scope, target, PT, KEY)
    if tr is not None and tr.textout is not None:
        ct = bytes(tr.textout); break
    print(f"  capture retry {attempt+1}...", flush=True); time.sleep(0.3)

if ct is None:
    print("NO RESPONSE from K82F (serial/clock/trigger). Check HS2 clock and JTAG wiring / replug Husky.", flush=True)
    scope.dis(); target.dis(); raise SystemExit(2)

print("plaintext :", bytes(PT).hex(), flush=True)
print("K82F ct   :", ct.hex(), flush=True)
print("expected  :", EXPECT, flush=True)
print("samples captured:", len(tr.wave), " (trigger works)" if tr.wave is not None and len(tr.wave) else " (no wave!)", flush=True)
ok = ct.hex() == EXPECT
print("KNOWN-ANSWER:", "OK - K82F hardware AES works through the Abductor" if ok else "MISMATCH", flush=True)
scope.dis(); target.dis()
print("DONE" if ok else "FAILED")
