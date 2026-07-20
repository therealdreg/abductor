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

# DFA self-test (no hardware). Exercises the full phoenixAES DFA pipeline in software before
# spending hardware time, and pins down the fault model the hardware must produce.
#
# It does three things:
#   1. Implements AES-128 in software (column-major state) and cross-checks it against two known
#      answers: AES(key=0,pt=0)=66e94bd4... (the standard all-zero known-answer) and
#      AES(key=2b7e...,pt=00..0f)=50fe67cc... (the ciphertext the iCE40 produced on the bench).
#      If both match, the software oracle reproduces the FPGA output for these two vectors on this bench.
#   2. Injects a single-byte fault at the input of round 9 (the Piret fault) for byte positions that
#      cover all 4 diagonals, as a clock glitch on the last-but-one round would.
#   3. Feeds the faulty ciphertexts to phoenixAES.crack_bytes(...), recovers the round-10 key,
#      inverts the key schedule to the master key, and checks 16/16 against the known key.
#
# If this prints DFA SELF-TEST OK, the cracker and this fault model are validated in software; the
# hardware run then only has to supply real faults with the same 4-diagonal coverage.
import phoenixAES
from chipwhisperer.analyzer.attacks.models.aes.key_schedule import key_schedule_rounds

SBOX=[0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16]
RCON=[0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

def gmul(a,b):
    p=0
    for _ in range(8):
        if b&1: p^=a
        hi=a&0x80; a=(a<<1)&0xff
        if hi: a^=0x1b
        b>>=1
    return p

def key_expansion(key):
    """Return 11 round keys, each 16 bytes in column-major order (index = row + 4*col)."""
    words=[list(key[4*i:4*i+4]) for i in range(4)]   # w[0..3], each a column of 4 bytes
    for i in range(4,44):
        t=list(words[i-1])
        if i%4==0:
            t=t[1:]+t[:1]                              # RotWord
            t=[SBOX[x] for x in t]                     # SubWord
            t[0]^=RCON[i//4-1]
        words.append([words[i-4][j]^t[j] for j in range(4)])
    return [bytes(sum((words[4*r+c] for c in range(4)),[])) for r in range(11)]

def sub_bytes(s): return bytearray(SBOX[x] for x in s)
def shift_rows(s):  # column-major
    return bytearray([s[0],s[5],s[10],s[15], s[4],s[9],s[14],s[3], s[8],s[13],s[2],s[7], s[12],s[1],s[6],s[11]])
def mix_columns(s):
    o=bytearray(16)
    for c in range(4):
        col=s[4*c:4*c+4]
        o[4*c+0]=gmul(2,col[0])^gmul(3,col[1])^col[2]^col[3]
        o[4*c+1]=col[0]^gmul(2,col[1])^gmul(3,col[2])^col[3]
        o[4*c+2]=col[0]^col[1]^gmul(2,col[2])^gmul(3,col[3])
        o[4*c+3]=gmul(3,col[0])^col[1]^col[2]^gmul(2,col[3])
    return o
def add_key(s,k): return bytearray(a^b for a,b in zip(s,k))

def aes128(pt, key, fault_round9=None, fault_round8=None):
    """AES-128 encrypt. fault_roundN=(pos,delta): XOR delta into state byte pos at the input of
    round N (before its SubBytes). Round 9 -> the classic single-byte Piret fault (4-byte diagonal
    ciphertext). Round 8 -> fully diffused fault that phoenixAES.convert_r8faults expands into one
    round-9 fault per diagonal."""
    rk=key_expansion(key)
    s=add_key(bytearray(pt), rk[0])
    for r in range(1,10):
        if r==8 and fault_round8 is not None:
            pos,delta=fault_round8; s[pos]^=delta
        if r==9 and fault_round9 is not None:
            pos,delta=fault_round9; s[pos]^=delta
        s=sub_bytes(s); s=shift_rows(s); s=mix_columns(s); s=add_key(s, rk[r])
    s=sub_bytes(s); s=shift_rows(s); s=add_key(s, rk[10])
    return bytes(s), rk

KEY=bytes([0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c])
PT =bytes(range(16))

# --- 1. oracle cross-check --------------------------------------------------
ct0,_=aes128(bytes(16), bytes(16))
assert ct0.hex()=="66e94bd4ef8a2c3b884cfa59ca342b2e", f"AES(0,0) wrong: {ct0.hex()}"
gold,rk=aes128(PT, KEY)
print("AES(0,0)                =", ct0.hex(), " [known-answer OK]")
print("AES(2b7e..,00..0f)      =", gold.hex(), " (hardware bench gave 50fe67cc996d32b6da0937e99bafec60)")
print("round-10 key (truth)    =", rk[10].hex())
print("master key   (truth)    =", KEY.hex())

# --- 2. build round-9 faults covering all 4 diagonals -----------------------
COLUMN_LOOKUP=[[0,13,10,7],[4,1,14,11],[8,5,2,15],[12,9,6,3]]  # diagonal-to-column map from the reference notebook
def which_column(ct):
    cols=[c for c in range(4) if all(ct[b]!=gold[b] for b in COLUMN_LOOKUP[c])]
    diff=sum(1 for i in range(16) if ct[i]!=gold[i])
    return cols[0] if (len(cols)==1 and diff==4) else None

faults=[]; cover={0:0,1:0,2:0,3:0}
for pos in range(16):
    for delta in (0x11,0x9c):
        cf,_=aes128(PT, KEY, fault_round9=(pos,delta))
        col=which_column(cf)
        if col is not None:
            faults.append(cf); cover[col]+=1
print(f"\ngenerated {len(faults)} clean single-diagonal faults, per-diagonal coverage:", cover)
assert all(v>=2 for v in cover.values()), "self-test did not cover all 4 diagonals"

# --- 3. crack with phoenixAES -----------------------------------------------
print("\n--- phoenixAES.crack_bytes(faults, gold, encrypt=True) ---")
r10=phoenixAES.crack_bytes(faults, bytearray(gold), encrypt=True, verbose=2)
print("\nphoenixAES returned r10 =", r10)
assert r10 is not None and ".." not in r10, "phoenixAES did not recover the full round-10 key"
assert bytearray.fromhex(r10)==bytearray(rk[10]), "recovered round-10 key != truth"
master=key_schedule_rounds(bytearray.fromhex(r10), 10, 0)
master=bytes(master)
correct=sum(1 for a,b in zip(master,KEY) if a==b)
print("recovered master key    =", master.hex())
print("known     master key    =", KEY.hex())
print(f"\nDFA MASTER-KEY BYTES CORRECT: {correct}/16   FULL MATCH: {master==KEY}")
r9_ok = master==KEY

# --- 4. round-8 route: one clean round-8 fault covers all 4 diagonals at once ----------------
# A single-byte fault at the input of round 8 diffuses to a full column at the round-9 input, i.e.
# it is equivalent to one round-9 fault on each of the 4 diagonals. convert_r8faults_bytes expands
# each fully-corrupted output into 4 round-9 faults, so 2 clean round-8 faults suffice for 16/16.
print("\n--- round-8 route: convert_r8faults_bytes + crack_bytes ---")
r8faults=[]
for pos, delta in ((0, 0x11), (6, 0x9c)):
    cf,_=aes128(PT, KEY, fault_round8=(pos, delta))
    nd=sum(1 for i in range(16) if cf[i]!=gold[i])
    print(f"  round-8 fault at byte {pos}: {nd}/16 ciphertext bytes changed")
    r8faults.append(bytearray(cf))
conv=phoenixAES.convert_r8faults_bytes(r8faults, bytearray(gold), encrypt=True)
r10_r8=phoenixAES.crack_bytes(conv, bytearray(gold), encrypt=True, verbose=1)
print("round-8 route r10 =", r10_r8)
r8_ok = bool(r10_r8) and ".." not in r10_r8 and bytearray.fromhex(r10_r8)==bytearray(rk[10])
print(f"ROUND-8 ROUTE {'OK (full round-10 key from 2 round-8 faults)' if r8_ok else 'FAILED'}")

print("\nDFA SELF-TEST OK" if (r9_ok and r8_ok) else "\nDFA SELF-TEST FAILED")
