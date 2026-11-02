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

# Differential fault attack (DFA) on the iCE40UP5K hardware AES. It follows the ChipWhisperer
# fault201 "Lab 1_3B - DFA Attack on AES": clock-glitch the AES core through HS2, keep the faulty
# ciphertexts that fit a fault model (round-9 faults and round-8 candidates), crack the round-10 key
# with phoenixAES, then invert the key schedule to get the master key.
# dfa_selftest.py checks the cracker on simulated round-9 and round-8 faults first.
#
# The core does one AES round per clock cycle, so which byte a glitch faults can depend on the data
# as well as the timing. The script runs a campaign on the known-answer plaintext, then one campaign
# per random plaintext, each with its own golden ciphertext, while any of the 4 diagonals of the
# round-10 key is unknown (25 campaigns at most). The round-10 key is the same for every plaintext,
# so partial keys merge by byte position.
#
# Needs the CW312T-iCE40UP on the straight board, the right-angle board or the CW313, and
# phoenixAES. On the UFO, take the SAM4S debug wires off J8 first. The script loads the
# iCE40UP5K_SS2 AES bitstream that ships with chipwhisperer.
#
# Usage: ice40_dfa_phoenix.py [label]
# label (default "abductor") goes into the log file name and the first log line. The log goes to the
# screen and to /home/dreg/chipwhisperer/dregdoc/ice40_dfa_<label>.txt and ends with DFA OK,
# DFA MISMATCH or DFA INCOMPLETE.
import sys, time, os, random
import chipwhisperer as cw
import phoenixAES
from chipwhisperer.analyzer.attacks.models.aes.key_schedule import key_schedule_rounds

LABEL = sys.argv[1] if len(sys.argv) > 1 else "abductor"
# Setup name for the log heading, from the label: cw313, ra, or anything else for the straight board.
SETUP = ("on CW313" if "cw313" in LABEL else
         "via right-angle Abductor" if LABEL == "ra" or LABEL.startswith("ra_") or LABEL.endswith("_ra") else
         "via Abductor")
KEY   = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
PT0   = bytearray(range(16))
GOLD0_KNOWN = "50fe67cc996d32b6da0937e99bafec60"       # known answer AES(KEY, PT0)
# COLUMN_LOOKUP[c] holds the ciphertext bytes of diagonal c: where state column c lands after the
# last ShiftRows. It is the column_lookup table of the fault201 lab.
COLUMN_LOOKUP = [[0,13,10,7],[4,1,14,11],[8,5,2,15],[12,9,6,3]]
OUT = f"/home/dreg/chipwhisperer/dregdoc/ice40_dfa_{LABEL}.txt"
random.seed(1234)                                       # same glitch points and plaintexts each run

scope = cw.scope(); scope.default_setup(); scope.adc.samples = 200   # only ciphertexts are used
target = cw.target(scope, cw.targets.CW305, force=True, platform='ss2_ice40', program=True)
time.sleep(0.5)
cw.set_all_log_levels(cw.logging.ERROR)
log = open(OUT, "w")
def emit(s):
    print(s, flush=True); log.write(s + "\n"); log.flush()

# phoenixAES has no __version__, so the log shows 0.0.5, the version in its setup.py.
emit(f"DFA (phoenixAES) on iCE40UP5K hardware AES via [{LABEL}]  ({phoenixAES.__name__} {getattr(phoenixAES,'__version__','0.0.5')})")

# A clock glitch can desync the SS2 UART, which runs on the same HS2 clock. The AES core still
# finishes, so only the serial link needs realigning: up to 6 tries of reset_comms, flush and echo.
# If they all fail, reconnect the target without reprogramming, which keeps the bitstream.
def resync():
    for _ in range(6):
        try:
            target.ss2.reset_comms(); target.ss2.flush(); target._ss2_test_echo()
            return True
        except Exception:
            time.sleep(0.05)
    try:
        globals()['target'] = cw.target(scope, cw.targets.CW305, force=True, platform='ss2_ice40', program=False)
        time.sleep(0.3); target._ss2_test_echo()
        return True
    except Exception:
        return False

# One encryption of pt. Returns the ciphertext, or None if the capture failed. An exception also
# triggers a resync.
def cap(pt):
    try:
        t = cw.capture_trace(scope, target, pt, KEY, ack=False)
    except Exception:
        resync(); return None
    return None if t is None else bytes(t.textout)

# Fault-free ciphertext for pt, with the glitch moved to ext_offset 4000, well past the AES window.
# Takes the first value seen twice in up to 8 captures, else the most common one (None if all fail).
def golden(pt):
    scope.glitch.width = 0; scope.glitch.offset = 0; scope.glitch.ext_offset = 4000
    seen = {}
    for _ in range(8):
        h = cap(pt)
        if h is None: continue
        seen[h] = seen.get(h, 0) + 1
        if seen[h] >= 2:
            return bytearray(h)
    return bytearray(max(seen, key=seen.get)) if seen else None

# Set up the clock glitch on HS2 (cglitch_setup without a second default_setup), a 0.1 s capture
# timeout and one glitch pulse per attempt. Then the known answer for PT0 must match.
scope.cglitch_setup(default_setup=False); scope.adc.timeout = 0.1; scope.glitch.repeat = 1
g0 = golden(PT0)
assert g0 is not None and g0.hex() == GOLD0_KNOWN, f"golden PT0 mismatch: {g0.hex() if g0 else None}"
emit(f"golden ct (PT0=00..0f) = {g0.hex()}   [known-answer OK]")

def classify(ct, gold):
    """Return c (0 to 3) if exactly 4 bytes changed and they are the bytes of diagonal c (the pattern
    of a clean round-9 fault), else None. This is the lab's check_column_glitch test plus the
    4-byte count."""
    if sum(1 for i in range(16) if ct[i] != gold[i]) != 4:
        return None
    for c in range(4):
        if all(ct[b] != gold[b] for b in COLUMN_LOOKUP[c]):
            return c
    return None

def attempt(pt, w, o, e):
    scope.glitch.width = w; scope.glitch.offset = o; scope.glitch.ext_offset = e
    return cap(pt)

# Random glitch point. Width and offset are in Husky Plus phase-shift steps, ext_offset in target
# clock cycles after the trigger. The band is chosen to fault the last rounds while rarely wedging
# the SS2 control FSM.
def rnd_params(ext_choices):
    return (random.randrange(2100, 3700, 2),      # width
            random.randrange(1500, 3100, 2),      # offset
            random.choice(ext_choices))

# r10 collects the round-10 key: 16 ints, None where unknown. merge() copies in every byte that a
# phoenixAES result string gives (hex, ".." where unknown) and never overwrites a known byte.
r10 = [None]*16
def merge(partial_hex):
    if not partial_hex: return
    for i in range(16):
        pair = partial_hex[2*i:2*i+2]
        if pair != ".." and r10[i] is None:
            r10[i] = int(pair, 16)
def have(c):   return all(r10[p] is not None for p in COLUMN_LOOKUP[c])
def missing(): return [c for c in range(4) if not have(c)]

# Two fault models:
#  Round 9 (Piret and Quisquater): a single-byte fault before the last MixColumns gives a 4-byte
#    diagonal ciphertext difference. phoenixAES needs 2 or more clean faults on each of the 4
#    diagonals. On this parallel core a fixed plaintext faults only one data-dependent diagonal, and
#    one diagonal was very rare across the plaintexts tried, so collecting all 4 this way is
#    impractical.
#  Round 8: a single-byte fault one round earlier diffuses to all 16 bytes.
#    phoenixAES.convert_r8faults_bytes turns one such output into round-9 faults on all 4 diagonals
#    at once, so in principle 2 clean round-8 faults from one plaintext give the whole round-10 key.
# So round 8 is the main route, and the round-9 faults found on the way are merged in too.
def diffcount(ct, gold): return sum(1 for i in range(16) if ct[i] != gold[i])

def try_round8(r8cand, gold):
    if len(r8cand) >= 2:
        conv = phoenixAES.convert_r8faults_bytes([bytearray(x) for x in r8cand], bytearray(gold), encrypt=True)
        merge(phoenixAES.crack_bytes(conv, bytearray(gold), encrypt=True, verbose=0))

def try_round9(r9faults, gold):
    if len(r9faults) >= 2:
        merge(phoenixAES.crack_bytes([bytearray(x) for x in r9faults], bytearray(gold), encrypt=True, verbose=0))

emit("\n=== DFA collection: round-8 route (primary) + round-9 route (bonus) ===")
r8_evidence = []
campaigns = 0
# One campaign: a plaintext, its golden ciphertext and up to `budget` attempts at random glitch
# points (ext_offset 0 to 9). Failed captures are skipped. The rest are classed by how many of the
# 16 bytes changed: 0 is normal; exactly 4, all in one diagonal, counts as a clean round-9 fault;
# 14 or more is a round-8 candidate; anything else is partial and dropped. Nothing checks that a
# candidate is a clean single-byte round-8 fault. A repeated output is counted again but kept once.
# After every 200 attempts, while a diagonal is missing, it cracks what it has and stops once the
# key is complete. It cracks once more at the end and keeps the first 6 candidates for the log.
def campaign(pt, budget):
    global campaigns
    campaigns += 1
    gold = golden(pt)
    if gold is None:
        emit(f"[pt {campaigns}] golden capture failed"); return
    r8cand = []; r9faults = []; stats = {"normal": 0, "r9": 0, "r8": 0, "partial": 0}
    for i in range(budget):
        if i and i % 200 == 0 and missing():
            try_round8(r8cand, gold); try_round9(r9faults, gold)
            if not missing(): break
        ct = attempt(pt, *rnd_params([0,1,2,3,4,5,6,7,8,9]))
        if ct is None: continue
        nd = diffcount(ct, gold)
        if nd == 0: stats["normal"] += 1; continue
        col = classify(ct, gold)
        if col is not None:
            stats["r9"] += 1
            if ct not in r9faults: r9faults.append(ct)
        elif nd >= 14:                                   # near-full corruption: round-8 candidate
            stats["r8"] += 1
            if ct not in r8cand: r8cand.append(ct)
        else:
            stats["partial"] += 1
    try_round8(r8cand, gold); try_round9(r9faults, gold)
    if r8cand:
        r8_evidence.append((pt.hex(), gold.hex(), [x.hex() for x in r8cand[:6]]))
    emit(f"[pt {campaigns}] {pt.hex()}  {stats}  r8cand={len(r8cand)} r9faults={len(r9faults)} "
         f"| key: {''.join('%02X'%x if x is not None else '..' for x in r10)}")

campaign(PT0, budget=3000)                               # known-answer plaintext first
while missing() and campaigns < 25:                      # then random ones, 25 campaigns at most
    campaign(bytearray(random.randrange(256) for _ in range(16)), budget=1500)

# Log up to 6 round-8 candidates for each of the first 5 plaintexts that had any. They passed only
# the 14-byte rule, and the log does not record which faults gave the key. The heading names the
# setup from the label.
emit(f"\n--- round-8 fault evidence (near-fully-corrupted outputs, real hardware {SETUP}) ---")
for pth, gh, fs in r8_evidence[:5]:
    emit(f"plaintext {pth}  golden {gh}")
    for f in fs: emit(f"    faulty ct {f}")

# With all 16 round-10 key bytes, invert the key schedule and compare the master key with KEY.
emit("\n=== RESULT ===")
if all(b is not None for b in r10):
    r10b = bytearray(r10)
    master = bytearray(key_schedule_rounds(r10b, 10, 0))
    correct = sum(1 for a, b in zip(master, KEY) if a == b)
    emit(f"recovered round-10 key : {r10b.hex()}")
    emit(f"recovered master key   : {master.hex()}")
    emit(f"known     master key   : {KEY.hex()}")
    emit(f"DFA MASTER-KEY BYTES CORRECT: {correct}/16   FULL MATCH: {master == KEY}")
    emit("DFA OK" if master == KEY else "DFA MISMATCH")
else:
    got = sum(1 for b in r10 if b is not None)
    emit(f"recovered {got}/16 round-10 key bytes; missing diagonals: {missing()}")
    emit("round-10 key partial   : " + ''.join("%02X" % x if x is not None else ".." for x in r10))
    emit("DFA INCOMPLETE")

log.close()
try: scope.dis()
except Exception: pass
try: target.dis()
except Exception: pass
print("DONE")
