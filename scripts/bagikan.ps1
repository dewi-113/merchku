# Bagikan Merchku yang berjalan di laptop ke teman (tanpa deploy).
#
#   powershell -ExecutionPolicy Bypass -File scripts\bagikan.ps1
#
# - Link Wi-Fi  : untuk teman di jaringan Wi-Fi yang sama.
# - Link publik : bila cloudflared terpasang (winget install Cloudflare.cloudflared),
#                 dibuat Cloudflare Quick Tunnel https://xxxx.trycloudflare.com
#                 yang bisa dibuka dari HP/PC mana saja selama jendela ini terbuka.
#
# Server dijalankan TANPA mode debug: debugger Flask tidak boleh terbuka ke orang lain.
param([int]$Port = 5000)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:FLASK_APP = 'run.py'
$env:FLASK_DEBUG = '0'

# IP Wi-Fi/LAN = adaptor yang punya default gateway (bukan VMware/WSL)
$lan = Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
    Select-Object -First 1 -ExpandProperty IPv4Address |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host ''
Write-Host '=== Merchku siap dibagikan ===' -ForegroundColor Cyan
Write-Host "Di laptop ini : http://127.0.0.1:$Port"
if ($lan) { Write-Host "Teman 1 Wi-Fi : http://${lan}:$Port" -ForegroundColor Green }
Write-Host '(Kalau link Wi-Fi tidak bisa dibuka, izinkan Python saat muncul pop-up Windows Firewall.)'
Write-Host ''

$server = Start-Process -FilePath 'python' -ArgumentList @('-m', 'flask', 'run', '--host', '0.0.0.0', '--port', "$Port", '--no-debugger', '--no-reload') -NoNewWindow -PassThru

try {
    # Terminal yang dibuka sebelum instalasi belum punya PATH baru, jadi cek juga lokasi bawaan winget.
    $cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflared) {
        $cloudflared = @("${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($cloudflared) {
        Write-Host 'Membuat link publik... cari baris https://....trycloudflare.com di bawah ini.' -ForegroundColor Cyan
        & $cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$Port"
    } else {
        Write-Host 'Link publik belum aktif: cloudflared belum terpasang.' -ForegroundColor Yellow
        Write-Host 'Pasang sekali saja:  winget install Cloudflare.cloudflared   lalu jalankan skrip ini lagi.'
        Write-Host 'Tekan Ctrl+C untuk berhenti.'
        Wait-Process -Id $server.Id
    }
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    Write-Host 'Server dihentikan, link sudah tidak aktif.'
}
