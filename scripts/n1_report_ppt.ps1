$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m app.n1_report_ppt @args
}
finally {
    Pop-Location
}
