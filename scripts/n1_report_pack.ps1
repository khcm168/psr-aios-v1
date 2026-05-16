$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m app.n1_report_pack @args
}
finally {
    Pop-Location
}
