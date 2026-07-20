#!/bin/bash
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

# FULL JTAG (not just SWD) of the CW312T-SAM4S via the Husky Plus (MPSSE) + OpenOCD.
# Reads the JTAG TAP IDCODE (which exercises the TDI -> chip -> TDO path), then halts and reads memory.
#
# Non-DIO MPSSE: the Husky drives JTAG on the main 20-pin SPI/PDI pins:
#   TCK=SCK, TMS=PDID, TDI=MOSI, TDO=MISO.
# Through the UFO+Abductor the bridge is 6 wires from the target-IO header to the UFO JTAG header J8:
#   SCK->J_TCK, PDID->J_TMS, MOSI->J_TDI, MISO->J_TDO, nRST->nRST, VREF->J_UREF.
# On the CW313 the same is done by mounting all of the JP3 caps.
OCDDIR=/home/dreg/chipwhisperer/openocd
VENV=/home/dreg/chipwhisperer/.venv/bin/python
PID=0xace6

echo "=== enable Husky MPSSE (non-DIO) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(1); print('MPSSE ON')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
sleep 1.5

echo "=== OpenOCD JTAG: scan chain (TAP IDCODE) + halt + read ==="
timeout 40 openocd -s "$OCDDIR" -f cw_openocd.cfg \
  -c "ftdi vid_pid 0x2b3e $PID" -c 'transport select jtag' \
  -f target/at91sam4sXX.cfg -c 'adapter speed 200' \
  -c 'init' \
  -c 'echo "--- JTAG scan chain ---"' -c 'scan_chain' \
  -c 'reset halt' \
  -c 'echo "--- SAM4S CHIPID_CIDR @0x400E0740 ---"' -c 'mdw 0x400e0740' \
  -c 'echo "--- FLASH @0x00400000 ---"' -c 'mdw 0x00400000 8' \
  -c 'echo "--- CPU pc ---"' -c 'reg pc' \
  -c 'shutdown' 2>&1

echo "=== disable MPSSE ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(0); print('MPSSE OFF')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
