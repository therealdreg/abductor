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

# SWD debug of the CW312T-SAM4S via the ChipWhisperer Husky Plus (MPSSE emulation) + OpenOCD.
#
# Works both on the CW313 baseboard (bridge made with the on-board JP3 caps) and THROUGH the
# UFO + Abductor (bridge made with 3 wires on the CW308: SCK->J_TCK, PDID->J_TMS, VREF->J_UREF).
#
# Non-DIO MPSSE: enable_MPSSE(1) puts SWD on the main 20-pin SPI/PDI pins -> PDID=SWDIO, SCK=SWCLK.
# The Husky Plus keeps USB PID 0xace6 in MPSSE mode. cw_openocd.cfg is the stock ChipWhisperer file.
OCDDIR=/home/dreg/chipwhisperer/openocd            # holds the stock cw_openocd.cfg
VENV=/home/dreg/chipwhisperer/.venv/bin/python
PID=0xace6

echo "=== enable Husky MPSSE (non-DIO SWD) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(1); print('MPSSE ON')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
sleep 1.5

echo "=== OpenOCD SWD: connect + halt + read ==="
timeout 40 openocd -s "$OCDDIR" -f cw_openocd.cfg \
  -c "ftdi vid_pid 0x2b3e $PID" -c 'transport select swd' \
  -f target/at91sam4sXX.cfg -c 'adapter speed 400' \
  -c 'init' -c 'reset halt' \
  -c 'echo "--- SAM4S CHIPID_CIDR @0x400E0740 ---"' -c 'mdw 0x400e0740' \
  -c 'echo "--- SRAM @0x20000000 ---"'              -c 'mdw 0x20000000 8' \
  -c 'echo "--- FLASH @0x00400000 (firmware) ---"'  -c 'mdw 0x00400000 16' \
  -c 'echo "--- CPU registers ---"' -c 'reg pc' -c 'reg sp' -c 'reg xPSR' \
  -c 'shutdown' 2>&1

echo "=== disable MPSSE (restore normal mode) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(0); print('MPSSE OFF')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
