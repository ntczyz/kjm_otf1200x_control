# AIBUS protocol (Yudian AI-series) — verified on AI-858

All values are little-endian. `addr` is the instrument address (1 in our setup).

## READ

Request, 8 bytes:

```
(0x80+addr), (0x80+addr), 0x52, param, 0x00, 0x00, crc_lo, crc_hi
crc = param * 256 + 0x52 + addr
```

Example (`addr=1`, `param=0x00`): `81 81 52 00 00 00 53 00`

Reply, **10 bytes, no header**:

```
PV_lo PV_hi  SV_lo SV_hi  MV  STATUS  DATA_lo DATA_hi  crc_lo crc_hi
crc = PV + SV + MV + STATUS*256 + DATA + addr
```

- `PV` and `SV` are in the instrument's display units (with `INP=0`, 0.1 °C:
  raw `216` = 21.6 °C).
- `MV` is 0–100 (percent output).
- `STATUS` low bits: `0` run, `1` stop, `2` hold; bit 3: 0 auto, 1 manual.
- `DATA` is the requested parameter value (signed 16-bit).

**Why "no reply" is usually wrong:** the reply does not start with a header.
Decoders that wait for `0x81 0x81 0x52` throw away every valid frame. Scan
10-byte windows over the received bytes and accept the first one whose CRC
matches.

## WRITE

```
(0x80+addr), (0x80+addr), 0x43, param, val_lo, val_hi, crc_lo, crc_hi
crc = param * 256 + 0x43 + addr + val
```

Example (`addr=1`, `param=0x1B` (`Srun`), `val=1`): `81 81 43 1B 01 00 60 00`

The instrument replies with the same 10-byte frame (read it to confirm).

## Parameter map (AI-858, as verified on hardware)

| Code | Name | Notes |
|---|---|---|
| 0x00 | PV / SV / MV / STATUS | live Process Value / Set Value |
| 0x07 | P | proportional band, raw 110 = 11.0 °C |
| 0x08 | I | integral, raw 660 = 66.0 s |
| 0x09 | d | derivative, raw 60 = 6.0 s |
| 0x0C | dPt | decimal point — **write 0–3, read adds +127** |
| 0x12 | OPL | output low limit (0 %) |
| 0x13 | OPH | output high limit (60 %) |
| 0x18 | AMAn | 0 none, 1 manual, 2 FSV, 3 on/off |
| 0x1A | MV | manual output 0–100 (writing it switches to MANUAL) |
| 0x1B | Srun | 0 run, 1 stop, 2 hold |
| 0x1E | SPL | setpoint low limit |
| 0x1F | SPH | setpoint high limit (32000) |
| 0x2A | SPr | ramp rate, **0.1 °C/min** |
| 0x2B | Pno | program number; 0 = program off, 50 = factory program |
| 0x4D | status register | bit0-1 run/stop/hold, bit3 auto/manual |
| 0x50.. | program SP/t pairs | SP1=0x50, t1=0x51, SP2=0x52, t2=0x53 … |

## Worked example — a real reply

Reading `param=0x00` from an idle AI-858 at 21.6 °C:

```
81 81 52 00 00 00 53 00        request
D8 00 00 00 00 3F 00 00 crc_lo crc_hi   reply
```

`PV = 0x00D8 = 216` → 21.6 °C, `SV = 0`, `MV = 0`, `STATUS = 0x3F` (auto+stop),
`DATA = 0`.

## Framing

- **8E1** when `AFC=9` (AI bus, even parity), **8N1** when `AFC=1`.
- 19200 baud typical (`bAud=0`).
- Some USB-RS485 adapters need a small inter-byte gap; sending all 8 bytes at
  once works with FTDI/FT231X.

## Reading many parameters

Loop `param` 0x00…0x36 with ~25 ms between frames, each time discarding the
input buffer and reading up to 64 bytes with a ~250 ms window. 55 parameters
take about 2 s. This is how the backup JSON files are produced.
