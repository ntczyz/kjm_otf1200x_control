# aibus-read.ps1 -- CORRECT AIBUS reader for Yudian AI-858 / AI-518P
# Reply has NO header: 10 bytes = PV(2) SV(2) MV(1) STATUS(1) DATA(2) CRC(2), all LE.
# CRC = (PV + SV + MV + STATUS*256 + DATA + Addr) & 0xFFFF
# Pure ASCII (Windows PowerShell 5.1).
[CmdletBinding()]
param(
  [string]$PortName = 'COM3',
  [int]$Baud = 19200,
  [int]$Addr = 1,
  [string]$Framing = '8E1',
  [int]$Samples = 5
)
$ErrorActionPreference = 'Continue'
function ToHex([byte[]]$b) { if ($null -eq $b -or $b.Length -eq 0) { return '' }; return ([System.BitConverter]::ToString($b)).Replace('-','') }
function S16([int]$v) { if ($v -gt 32767) { return ($v - 65536) }; return $v }
function New-Aibus([int]$a, [int]$code) {
  $cs = ($code * 256 + 0x52 + $a) -band 0xFFFF
  return [byte[]]([byte](0x80+$a), [byte](0x80+$a), [byte]0x52, [byte]$code, 0, 0, [byte]($cs -band 0xFF), [byte](($cs -shr 8) -band 0xFF))
}
function Decode-Aibus([byte[]]$r, [int]$a) {
  if ($null -eq $r -or $r.Length -lt 10) { return $null }
  for ($o = 0; $o -le ($r.Length - 10); $o++) {
    $pv = [int]$r[$o] + 256*[int]$r[$o+1]
    $sv = [int]$r[$o+2] + 256*[int]$r[$o+3]
    $mv = [int]$r[$o+4]
    $st = [int]$r[$o+5]
    $dat = [int]$r[$o+6] + 256*[int]$r[$o+7]
    $crc = [int]$r[$o+8] + 256*[int]$r[$o+9]
    $calc = ($pv + $sv + $mv + $st*256 + $dat + $a) -band 0xFFFF
    if ($calc -eq $crc) {
      return [pscustomobject]@{
        PVRaw=$pv; SVRaw=$sv; MV=[int](S16 $mv); Status=$st; Data=[int](S16 $dat)
        Crc=$crc; Raw=(ToHex ($r[$o..($o+9)])); Offset=$o
      }
    }
  }
  return $null
}
$par = [System.IO.Ports.Parity]::None
$stop = [System.IO.Ports.StopBits]::One
if ($Framing -eq '8E1') { $par = [System.IO.Ports.Parity]::Even }
if ($Framing -eq '8E2') { $par = [System.IO.Ports.Parity]::Even; $stop = [System.IO.Ports.StopBits]::Two }
if ($Framing -eq '8N2') { $stop = [System.IO.Ports.StopBits]::Two }

$sp = New-Object System.IO.Ports.SerialPort($PortName, $Baud, $par, 8, $stop)
$sp.ReadTimeout = 200; $sp.WriteTimeout = 400
$sp.DtrEnable = $false; $sp.RtsEnable = $false
$sp.Open()
Write-Host ("=== AIBUS read  port={0} {1} {2}  addr={3} ===" -f $PortName, $Baud, $Framing, $Addr)

$frame = New-Aibus $Addr 0x00
Write-Host ("TX (read SV, PV comes back too): " + (ToHex $frame))
$ok = 0
for ($i = 1; $i -le $Samples; $i++) {
  $sp.DiscardInBuffer()
  $sp.Write($frame, 0, $frame.Length)
  $rx = New-Object System.Collections.ArrayList
  $sw = New-Object System.Diagnostics.Stopwatch; $sw.Start()
  while ($sw.ElapsedMilliseconds -lt 400) {
    while ($sp.BytesToRead -gt 0 -and $rx.Count -lt 64) { [void]$rx.Add([byte]$sp.ReadByte()) }
    Start-Sleep -Milliseconds 2
  }
  $arr = $rx.ToArray()
  $d = Decode-Aibus $arr $Addr
  if ($null -ne $d) {
    $ok++
    # dPt: read code 0x0C to know decimal point
    $t = $d.PVRaw / 10.0
    Write-Host ("  #{0} raw={1}  PV={2} ({3:N1} C assumed dPt=1)  SV={4}  MV={5}  ST=0x{6:X2}  crc=0x{7:X4} OK  rx={8}" -f `
      $i, $d.PVRaw, $d.PVRaw, $t, $d.SVRaw, $d.MV, $d.Status, $d.Crc, $d.Raw)
  } else {
    Write-Host ("  #{0} NO VALID REPLY  rx({1}B)={2}" -f $i, $arr.Length, (ToHex $arr))
  }
  Start-Sleep -Milliseconds 150
}
$sp.Close(); $sp.Dispose()
Write-Host ("`nvalid replies: {0}/{1}" -f $ok, $Samples)
