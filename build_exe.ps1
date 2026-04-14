$ErrorActionPreference = 'Stop'
$py = 'C:\Users\AdamWalker\AppData\Local\Programs\Python\Python312\python.exe'

Write-Host 'Installing build dependencies...'
& $py -m pip install -e .[dev]

Write-Host 'Building WashingMachine.exe...'
& $py -m PyInstaller --noconfirm --clean .\washing-machine.spec

Write-Host ''
Write-Host 'Build complete.'
Write-Host 'EXE folder:' (Resolve-Path .\dist\WashingMachine)
