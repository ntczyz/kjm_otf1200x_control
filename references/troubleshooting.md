# Troubleshooting tree

Work top-down; each step answers one question and removes half the possibilities.

## Step 0 — is the port there?

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
pnputil /enum-devices /class Ports
```

If the adapter is absent: check the USB cable, try another port, re-plug.
No serial port means no protocol debugging.

## Step 1 — does ANY byte come back?

```
request 81 81 52 00 00 00 53 00  →  how many bytes do you read?
```

| Result | Meaning | Check |
|---|---|---|
| 0 bytes | instrument not answering | address (`Addr`), wiring A/B swapped, parity/baud, `bAud` re-purposed, RTS/DTR |
| some bytes, not 10 | framing/noise | parity (8E1 vs 8N1), baud, adapter |
| 10 bytes | good — continue | |

If the adapter is a plain USB-UART, a 2-wire RS485 link may need TX/RX bridged
(1↔3, 2↔4 on the DB9) or a real RS485 adapter.

## Step 2 — is the frame valid?

Check `CRC = PV + SV + MV + STATUS*256 + DATA + Addr`. If the CRC never matches,
you are probably reading the wrong framing or the wrong address.

## Step 3 — are the numbers plausible?

- `PV=216` with `INP=0` means 21.6 °C, not 216 °C.
- `PV` stuck at a constant weird value → sensor type (`Sn`) wrong.
- `PV` = 0 and `STATUS` shows a fault → open thermocouple.

## Step 4 — can you control it?

| Symptom | Cause | Fix |
|---|---|---|
| MV writes but the heater stays cold | state is `StoP` | write `Srun=0` |
| MV writes but PV does not move | manual mode + StoP, or OPH=0 | check `0x4D` bit 3 and `OPH` |
| Setpoint does not ramp | `Pno ≠ 0` (program) or `SPr=0` | write `Pno=0`, then `SPr` |
| Ramp is 10x too slow | `SPr` is 0.1 °C/min | `SPr = rate × 10` |
| Overshoot at the top | SV + SPr lead the PV | lower `SPr`, or accept 1–2 % overshoot |

## Step 5 — restore

```
MV=0 → Srun=1 → AMAn=1 → Srun=0 → Srun=1 → AMAn=2
```

Then read all 55 parameters and diff against the pre-run backup. Expect 0
differences and `0x4D = 0x3F01` (auto + stop).

## Step 6 — logging looks wrong?

- Empty or header-only CSV → the writer opened the file in the wrong mode, or an
  exception killed the loop; check the `finally`/restore path.
- Columns shifted → thousands separators in the formatted numbers (see
  pitfalls §7).
- Missing rows during a run → serial timeouts; retry once before aborting.

## Step 7 — the web page is stale

- `fetch('/data.csv')` returns 404 → the server route or the file glob is wrong.
- Page never updates → the JS interval stopped (an exception in `draw()`), or the
  browser cached the CSV (use `cache: 'no-store'` and a `?ts=` query).
- Hover crosshair disappears on refresh → the page is reloading instead of
  redrawing (see pitfalls §10).
