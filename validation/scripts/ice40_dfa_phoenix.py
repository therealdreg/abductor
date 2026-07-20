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

# DFA on the iCE40UP5K hardware AES via the Abductor, using phoenixAES.
# This mirrors the ChipWhisperer fault201 "Lab 1_3B - DFA Attack on AES" workflow:
#   * clock-glitch the FPGA on the last-but-one round (round 9),
#   * keep only clean single-column faults (the check_column_glitch filter),
#   * feed the faulty ciphertexts to phoenixAES.crack_bytes(...) to get the round-10 key,
#   * invert the key schedule to the master key.
# The cracker + fault model are already shown to match this FPGA byte-for-byte in dfa_selftest.py.
#
# The FPGA AES is a parallel core (1 round/cycle), so which byte a glitch faults can depend on the
# DATA, not just timing. Piret DFA needs all 4 diagonals. So this is ADAPTIVE:
#   Phase 1: fixed plaintext, broad randomized glitch scan; if it covers all 4 diagonals -> crack.
#   Phase 2: for any missing diagonal, try fresh plaintexts (each with its own golden ct) and crack
#            that quarter of the round-10 key separately, then merge. The round-10 key is the same
#            for every plaintext, so partial results merge by position.
# Usage: ice40_dfa_phoenix.py [label]
import sys, time, os, random
import chipwhisperer as cw
import phoenixAES
from chipwhisperer.analyzer.attacks.models.aes.key_schedule import key_schedule_rounds

LABEL = sys.argv[1] if len(sys.argv) > 1 else "abductor"
KEY   = bytearray([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
PT0   = bytearray(range(16))
GOLD0_KNOWN = "50fe67cc996d32b6da0937e99bafec60"       # matches software AES(KEY,PT0)
COLUMN_LOOKUP = [[0,13,10,7],[4,1,14,11],[8,5,2,15],[12,9,6,3]]   # diagonal map
OUT = f"/home/dreg/chipwhisperer/dregdoc/ice40_dfa_{LABEL}.txt"
random.seed(1234)                                       # reproducible scan order

scope = cw.scope(); scope.default_setup(); scope.adc.samples = 200
target = cw.target(scope, cw.targets.CW305, force=True, platform='ss2_ice40', program=True)
time.sleep(0.5)
cw.set_all_log_levels(cw.logging.ERROR)
log = open(OUT, "w")
def emit(s):
    print(s, flush=True); log.write(s + "\n"); log.flush()

emit(f"DFA (phoenixAES) on iCE40UP5K hardware AES via [{LABEL}]  ({phoenixAES.__name__} {getattr(phoenixAES,'__version__','0.0.5')})")

# ---- resync: a clock glitch can desync the SS2 UART (shared HS2 clock). The AES core still
# finishes; we just need to realign the serial link. reset_comms + echo restores it; if that
# fails a few times, re-create the target WITHOUT reprogramming (keeps the bitstream). ----
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

def cap(pt):
    try:
        t = cw.capture_trace(scope, target, pt, KEY, ack=False)
    except Exception:
        resync(); return None
    return None if t is None else bytes(t.textout)

# ---- golden ciphertext: capture with the glitch pushed well past the AES window ----
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

# ---- sanity: known-answer for PT0 must match ----
scope.cglitch_setup(default_setup=False); scope.adc.timeout = 0.1; scope.glitch.repeat = 1
g0 = golden(PT0)
assert g0 is not None and g0.hex() == GOLD0_KNOWN, f"golden PT0 mismatch: {g0.hex() if g0 else None}"
emit(f"golden ct (PT0=00..0f) = {g0.hex()}   [known-answer OK]")

def classify(ct, gold):
    """Return the single glitched column (0..3) if exactly one column's 4 bytes changed, else None."""
    if sum(1 for i in range(16) if ct[i] != gold[i]) != 4:
        return None
    for c in range(4):
        if all(ct[b] != gold[b] for b in COLUMN_LOOKUP[c]):
            return c
    return None

def attempt(pt, w, o, e):
    scope.glitch.width = w; scope.glitch.offset = o; scope.glitch.ext_offset = e
    return cap(pt)

# glitch search space (Husky glitch units). A moderate band: strong enough to fault the last rounds,
# mild enough that it rarely wedges the SS2 control FSM (on this bench, no comms resyncs were needed).
def rnd_params(ext_choices):
    return (random.randrange(2100, 3700, 2),      # width
            random.randrange(1500, 3100, 2),      # offset
            random.choice(ext_choices))

# merge helper: fill a partial round-10 key (16 ints or None) from a phoenixAES partial hex string
r10 = [None]*16
def merge(partial_hex):
    if not partial_hex: return
    for i in range(16):
        pair = partial_hex[2*i:2*i+2]
        if pair != ".." and r10[i] is None:
            r10[i] = int(pair, 16)
def have(c):   return all(r10[p] is not None for p in COLUMN_LOOKUP[c])
def missing(): return [c for c in range(4) if not have(c)]

# ---- collection: round-8 route (primary) + round-9 route (bonus) -----------
# Two DFA routes, both shown to match this FPGA byte-for-byte in dfa_selftest.py:
#  * round-9 (Piret): a single-byte fault before the last MixColumns yields a 4-byte diagonal ct
#    diff; needs >=2 clean faults on EACH of the 4 diagonals. On this parallel FPGA a fixed plaintext
#    only faults one DATA-dependent diagonal and diagonal 1 is very rare -> coverage is impractical.
#  * round-8: a single-byte fault one round earlier fully diffuses; phoenixAES.convert_r8faults_bytes
#    expands ONE such fully-corrupted output into a round-9 fault on ALL 4 diagonals at once, so just
#    2 clean round-8 faults from a SINGLE plaintext recover the whole round-10 key -- no diagonal hunt.
# Round-8 is therefore primary: fix a plaintext, glitch a round earlier, collect near-fully-corrupted
# outputs, convert + crack. Any round-9 diagonal faults seen on the way are merged in as a bonus.
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
def campaign(pt, budget):
    global campaigns
    campaigns += 1
    gold = golden(pt)
    if gold is None:
        emit(f"[pt {campaigns}] golden capture failed"); return
    r8cand = []; r9faults = []; stats = {"normal": 0, "r9": 0, "r8": 0, "partial": 0}
    for i in range(budget):
        ct = attempt(pt, *rnd_params([0,1,2,3,4,5,6,7,8,9]))
        if ct is None: continue
        nd = diffcount(ct, gold)
        if nd == 0: stats["normal"] += 1; continue
        col = classify(ct, gold)
        if col is not None:
            stats["r9"] += 1
            if ct not in r9faults: r9faults.append(ct)
        elif nd >= 14:                                   # near-full corruption -> round-8 candidate
            stats["r8"] += 1
            if ct not in r8cand: r8cand.append(ct)
        else:
            stats["partial"] += 1
        if (i + 1) % 200 == 0 and missing():
            try_round8(r8cand, gold); try_round9(r9faults, gold)
            if not missing(): break
    try_round8(r8cand, gold); try_round9(r9faults, gold)
    if r8cand:
        r8_evidence.append((pt.hex(), gold.hex(), [x.hex() for x in r8cand[:6]]))
    emit(f"[pt {campaigns}] {pt.hex()}  {stats}  r8cand={len(r8cand)} r9faults={len(r9faults)} "
         f"| key: {''.join('%02X'%x if x is not None else '..' for x in r10)}")

campaign(PT0, budget=3000)                               # primary shot on the known-answer plaintext
while missing() and campaigns < 25:                      # each fresh plaintext is another round-8 shot
    campaign(bytearray(random.randrange(256) for _ in range(16)), budget=1500)

emit("\n--- round-8 fault evidence (near-fully-corrupted outputs, real hardware via the Abductor) ---")
for pth, gh, fs in r8_evidence[:5]:
    emit(f"plaintext {pth}  golden {gh}")
    for f in fs: emit(f"    faulty ct {f}")

# ---- assemble & verify ----
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
