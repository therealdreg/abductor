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

# SWD debug of the CW312T-SAM4S with the Husky Plus in MPSSE mode (its FTDI emulation) and OpenOCD:
# reset and halt the core, then read the chip ID, SRAM, flash and core registers.
#
# On the CW313 the on-board JP3 jumpers make the bridge. Through the UFO and the Abductor, the
# bridge is wires 1 to 3 from the UFO's J5 header to its J8 header (README "Using the board"):
# SCK to J_TCK (SWCLK), PDID/CS to J_TMS (SWDIO) and VREF to J_VREF (JTAG_VREF for the pull-ups).
# Without the VREF wire, OpenOCD failed with "cannot read IDR". Wire 4, nRST to J_TRST, was also
# fitted on the bench, but J_TRST is JTAG TRST (CW312 edge A32), not a reset, and OpenOCD drives
# no reset line.
#
# Non-DIO MPSSE: enable_MPSSE(1) puts SWD on the main 20-pin SPI/PDI pins, PDID as SWDIO and SCK as
# SWCLK. The script turns MPSSE mode on first and off at the end. The Husky Plus keeps USB PID
# 0xace6 in MPSSE mode. cw_openocd.cfg is the stock ChipWhisperer file. No arguments. Prints the
# OpenOCD output and saves no file.
OCDDIR=/home/dreg/chipwhisperer/openocd            # holds the stock cw_openocd.cfg
VENV=/home/dreg/chipwhisperer/.venv/bin/python
PID=0xace6

echo "=== enable Husky MPSSE (non-DIO SWD) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(1); print('MPSSE ON')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
sleep 1.5

echo "=== OpenOCD SWD: connect + halt + read ==="
# adapter speed is in kHz. reset halt resets the core through SYSRESETREQ (cortex_m reset_config
# sysresetreq in the at91sam4 target config). mdw reads 32-bit words. timeout stops OpenOCD after
# 40 s if it hangs.
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
