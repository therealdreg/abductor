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

# Flash a CW312T-K82F (NXP Kinetis MK82F) through the ChipWhisperer Husky Plus (MPSSE) + OpenOCD.
# The K82F does have a ROM serial bootloader (KBOOT), but NewAE recommends flashing over SWD/JTAG, the path used here. It needs the same 4 debug wires
# on the CW308 UFO J8 that the SAM4S SWD used:
#   UFO SCK  -> J8 J_TCK   (SWCLK)
#   UFO PDID -> J8 J_TMS   (SWDIO)
#   UFO VREF -> J8 J_UREF  (debug reference)
#   UFO nRST -> J8 J_TRST  (reset; kx.cfg uses srst)
# Non-DIO MPSSE puts SWD on the main 20-pin SPI/PDI pins. Husky Plus keeps USB PID 0xace6 in MPSSE.
# Usage: k82f_flash.sh <firmware.hex|elf>
set -o pipefail
HEX="${1:?usage: k82f_flash.sh <firmware.hex|.elf>}"
OCDDIR=/home/dreg/chipwhisperer/openocd            # stock cw_openocd.cfg
VENV=/home/dreg/chipwhisperer/.venv/bin/python
PID=0xace6

echo "=== enable Husky MPSSE (non-DIO SWD) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(1); print('MPSSE ON')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
sleep 1.5

echo "=== OpenOCD SWD: flash $HEX (kx.cfg) ==="
timeout 120 openocd -s "$OCDDIR" -f cw_openocd.cfg \
  -c "ftdi vid_pid 0x2b3e $PID" -c 'transport select swd' \
  -f target/kx.cfg -c 'adapter speed 1000' \
  -c 'init' -c 'reset halt' -c 'kinetis disable_wdog' \
  -c "program $HEX verify reset" \
  -c 'shutdown' 2>&1

echo "=== disable MPSSE (restore normal capture mode) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(0); print('MPSSE OFF')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
