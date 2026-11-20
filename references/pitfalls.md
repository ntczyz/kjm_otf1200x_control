# Pitfalls found on real hardware

Every item below cost real debugging time on an MTI OTF-1200X + Yudian AI-858.

## 1. The AIBUS reply has no header

The reply is `PV SV MV STATUS DATA CRC` — 10 bytes starting directly with the PV
low byte. A decoder that requires `0x81 0x81 0x52` at the start discards every
valid frame and reports "no reply". Scan 10-byte windows and check the CRC.

## 2. `SPr` is 0.1 °C/min

`SPr=27` gives **2.7 °C/min**, not 27. For 45 °C/min write `SPr=450`.
The old script silently produced a 10x-slow ramp for this reason.

## 3. `StoP` disables the output — even in manual mode

With the instrument in StoP, writing MV leaves the heater at 0 and PV just sits
at room temperature. Write `Srun=0` to clear StoP.

## 4. Writing `AMAn` does not switch manual → auto

`AMAn=0/1/2/3` changes only the parameter. The working state stays manual.
Writing **`Srun=0` forces AUTO** — that is the reliable way back.

## 5. `bAud` can silently kill the COMM port

`bAud` 4 / 8 / 12 re-purpose the COMM connector as 4–20 mA output / switch input
/ alarm output. After such a change there is no communication at all — and no
amount of protocol work will help.

## 6. `dPt` write range is 0–3, read adds +127

- write `0` → read `128` (1 decimal internally, display without a decimal)
- write `1` → read `1` (display shows 0.1 °C)
- writing `128` directly is clamped to `1` — do **not** write the read-back value.

## 7. CSV thousands separators corrupt the log

`"{0:N1}" -f 1198.6` writes `1,198.6`, which splits a CSV line into two columns.
Use `[string]::Format([CultureInfo]::InvariantCulture, "{0:0.0}", $v)`.

## 8. PowerShell 5.1 traps in the helper scripts

- `[Convert]::ToHexString` does not exist in 5.1 → use
  `[BitConverter]::ToString($bytes).Replace('-','')`.
- Function names `R`, `Rd` collide with the built-in aliases `Invoke-History` and
  `Remove-Item`. Use scriptblocks or unique names.
- `for($x in ...)` is C# syntax — PowerShell needs `foreach($x in ...)`.
- `New-Object System.IO.Ports.SerialPort(port, baud, parity, ...)` rejects enum
  literals inline; assign the enum members to variables first.

## 9. The serial adapter re-enumerates

The port changed across days (COM3 → COM4 → COM5 → COM6). Always re-check with
`[System.IO.Ports.SerialPort]::GetPortNames()` before a run, and remember that a
plain USB-UART (FT232/PL2303) is not a real RS485 transceiver — a 2-wire link
may need TX/RX bridged or a proper RS485 adapter.

## 10. A full page reload kills the hover crosshair

`<meta http-equiv="refresh">` (or a JS `location.reload()` loop) wipes any canvas
crosshair every few seconds. For a live dashboard, fetch the CSV with
`fetch()` and redraw the canvas in place — the hover state survives and the data
still updates every 2 s.

## 11. Writing `MV` switches the instrument to MANUAL

Any write to 0x1A puts the controller in manual, and the furnace then holds that
output forever. Always finish a manual run with the restore sequence:

```
MV=0 → Srun=1 → AMAn=1 → Srun=0 → Srun=1 → AMAn=2 (FSV)
```

and verify 55 parameters against the pre-run backup.

## 12. Fitted ambient temperature is not identifiable

In a two-exponential cooling fit `T_amb` is strongly correlated with `A2` and
`τ2`; the optimiser will happily report 18–33 °C for the same data. Report the
time constants, not the fitted ambient. Fitted τ values are trustworthy.

## 13. MV does not have to be continuous

The furnace accepts coarse MV steps. Writing every 5 s and only when |Δ| ≥ 2 %
reduces serial traffic and works at least as well as 1 Hz updates.

## 14. The panel display is not a text display

The AI-858 shows numbers / fixed firmware symbols on 7-segment digits. There is
no AIBUS command to write arbitrary display text, and the SV window only shows
about three significant digits in practice. Do not promise "hello" on the panel.
