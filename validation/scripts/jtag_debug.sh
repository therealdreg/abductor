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

# Full JTAG debug of the CW312T-SAM4S with the Husky Plus in MPSSE mode and OpenOCD. JTAG also uses
# TDI and TDO, which SWD (swd_debug.sh) leaves unused. The script scans the chain for the TAP
# IDCODE, then resets and halts the core and reads the chip ID, flash and pc. The IDCODE comes out
# on TDO, so it checks TDO; the halt and the reads after it shift their commands in on TDI, so they
# check TDI. The script turns MPSSE mode on first and off at the end.
#
# Non-DIO MPSSE: the Husky Plus drives JTAG on the main 20-pin SPI/PDI pins: TCK on SCK, TMS on
# PDID, TDI on MOSI and TDO on MISO.
# Through the UFO and the Abductor the bridge is wires from the UFO's J5 header to its J8 header
# (README "Using the board"): SCK to J_TCK, PDID/CS to J_TMS, VREF to J_VREF, MOSI to J_TDI and
# MISO to J_TDO. The JTAG log shows a sixth wire from nRST to J8's nRST pin (JTAG_nRST, CW312
# edge A31, which the SAM4S ties to its nRST); OpenOCD drives no reset line, so it is optional.
# On the CW313 the JP3 caps make the same bridge.
# No arguments. Prints the OpenOCD output and saves no file.
OCDDIR=/home/dreg/chipwhisperer/openocd
VENV=/home/dreg/chipwhisperer/.venv/bin/python
PID=0xace6

echo "=== enable Husky MPSSE (non-DIO) ==="
$VENV -c "import chipwhisperer as cw; s=cw.scope(); s.enable_MPSSE(1); print('MPSSE ON')" 2>&1 \
  | grep -vE "changed from|Unexpected start" | tail -1
sleep 1.5

echo "=== OpenOCD JTAG: scan chain (TAP IDCODE) + halt + read ==="
# adapter speed is in kHz. reset halt resets the core through SYSRESETREQ (cortex_m reset_config
# sysresetreq in the at91sam4 target config). mdw reads 32-bit words. timeout stops OpenOCD after
# 40 s if it hangs.
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
