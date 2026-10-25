# Arranca Zyra en tu ordenador accesible desde el móvil (misma red WiFi). Solo para pruebas:
#   .\scripts\movil.ps1            (puerto 8000)   |   .\scripts\movil.ps1 -Port 8080
# Fuerza DJANGO_DEBUG=True solo en esta sesión; no toca el .env ni sirve para producción.
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$ip = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -match '^(192\.168|10\.|172\.(1[6-9]|2\d|3[01]))\.' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host ""
if ($ip) { Write-Host "En el móvil (misma WiFi) abre:  http://${ip}:$Port" -ForegroundColor Green }
else { Write-Host "No encuentro tu IP de WiFi; mírala con ipconfig (IPv4)." -ForegroundColor Yellow }
Write-Host "Si no carga: permite Python en el Firewall de Windows (red privada)." -ForegroundColor Cyan
Write-Host ""

$env:DJANGO_DEBUG = 'True'
python manage.py runserver "0.0.0.0:$Port"
