param([switch]$ValidateLayout)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ErrorActionPreference = "Stop"

$Projects = [ordered]@{
    ARM = [pscustomobject]@{
        Name = "ARM"
        Root = "C:\Dev\ARM"
        Launcher = "OPEN_ARM_RUNBOOK.bat"
        Runbook = "RUNBOOK.md"
        Accent = [System.Drawing.Color]::FromArgb(185, 32, 45)
        Checks = @(
            "automations\check_environment.bat",
            "automations\webapp_health.bat",
            "automations\preview_queue.bat"
        )
    }
    CRM = [pscustomobject]@{
        Name = "CRM"
        Root = "C:\Dev\CRM"
        Launcher = "OPEN_RUNBOOK.bat"
        Runbook = "RUNBOOK.md"
        Accent = [System.Drawing.Color]::FromArgb(24, 96, 72)
        Checks = @(
            "automations\check_environment.bat",
            "automations\preview_today.bat"
        )
    }
    LINE = [pscustomobject]@{
        Name = "LINE"
        Root = "C:\Dev\line_edge_selenium"
        Launcher = "OPEN_LINE_RUNBOOK.bat"
        Runbook = "LINE_RUNBOOK.md"
        Accent = [System.Drawing.Color]::FromArgb(32, 128, 104)
        Checks = @(
            "automations\10_LINE_Message_Test\worker_status.cmd",
            "automations\15_Material_Vision_Index\status.cmd"
        )
    }
    EasyFlow = [pscustomobject]@{
        Name = "EasyFlow"
        Root = "C:\Dev\EasyFlowExpense"
        Launcher = "OPEN_RUNBOOK.bat"
        Runbook = "RUNBOOK.md"
        Accent = [System.Drawing.Color]::FromArgb(39, 104, 176)
        Checks = @(
            "automations\check_environment.bat",
            "automations\ensure_sheet.bat",
            "automations\preview_keyin_rows.bat"
        )
    }
}

function Test-PathText {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        return "OK"
    }
    return "MISSING"
}

function Start-ProjectLauncher {
    param($Project)
    $launcher = Join-Path $Project.Root $Project.Launcher
    if (-not (Test-Path -LiteralPath $launcher)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing launcher:`r`n$launcher",
            "Z13 Launch Menu",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }

    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = "cmd.exe"
    $info.Arguments = "/d /c call `"$launcher`""
    $info.WorkingDirectory = $Project.Root
    $info.UseShellExecute = $true
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($info) | Out-Null
    $script:StatusLabel.Text = "Opened $($Project.Name) operator console."
}

function Open-ProjectFolder {
    param($Project)
    if (-not (Test-Path -LiteralPath $Project.Root)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing project folder:`r`n$($Project.Root)",
            "Z13 Launch Menu",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }
    Start-Process explorer.exe -ArgumentList "`"$($Project.Root)`""
    $script:StatusLabel.Text = "Opened folder: $($Project.Root)"
}

function Open-ProjectRunbook {
    param($Project)
    $runbook = Join-Path $Project.Root $Project.Runbook
    if (-not (Test-Path -LiteralPath $runbook)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing runbook:`r`n$runbook",
            "Z13 Launch Menu",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }
    Start-Process notepad.exe -ArgumentList "`"$runbook`""
    $script:StatusLabel.Text = "Opened runbook: $($Project.Name)"
}

function Start-SequentialChecks {
    param($Project)
    if (-not (Test-Path -LiteralPath $Project.Root)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing project folder:`r`n$($Project.Root)",
            "Z13 Launch Menu",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }

    $safeName = $Project.Name -replace '[^A-Za-z0-9_-]', '_'
    $tempCmd = Join-Path $env:TEMP ("z13_{0}_readonly_checks.cmd" -f $safeName)
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("@echo off")
    $lines.Add("setlocal")
    $lines.Add("title Z13 $($Project.Name) read-only checks")
    $lines.Add("cd /d `"$($Project.Root)`"")
    $lines.Add("echo === Z13 $($Project.Name) read-only daily checks ===")
    $lines.Add("echo Project: $($Project.Root)")
    $lines.Add("echo.")
    foreach ($relative in $Project.Checks) {
        $lines.Add("echo ---- $relative ----")
        $lines.Add("if exist `"$relative`" (")
        $lines.Add("  call `"$relative`"")
        $lines.Add(") else (")
        $lines.Add("  echo Missing: $relative")
        $lines.Add(")")
        $lines.Add("echo.")
    }
    $lines.Add("echo Finished $($Project.Name) read-only checks.")
    $lines.Add("pause")
    [System.IO.File]::WriteAllLines($tempCmd, $lines, [System.Text.Encoding]::ASCII)

    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = "cmd.exe"
    $info.Arguments = "/d /c `"$tempCmd`""
    $info.WorkingDirectory = $Project.Root
    $info.UseShellExecute = $true
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($info) | Out-Null
    $script:StatusLabel.Text = "Started read-only checks for $($Project.Name)."
}

function Get-GitSummary {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        return "No .git folder"
    }
    try {
        $output = & git -C $Root status --short --branch 2>&1
        if ($LASTEXITCODE -ne 0) {
            return ($output | Select-Object -First 2) -join " | "
        }
        $lines = @($output)
        if ($lines.Count -eq 1) {
            return $lines[0]
        }
        return ("{0} | {1} changed item(s)" -f $lines[0], ($lines.Count - 1))
    }
    catch {
        return "Git status unavailable: $($_.Exception.Message)"
    }
}

function Get-LatestLogText {
    param([string]$Root)
    $logRoot = Join-Path $Root "data\logs"
    if (-not (Test-Path -LiteralPath $logRoot)) {
        return "No data\logs folder"
    }
    try {
        $latest = Get-ChildItem -LiteralPath $logRoot -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($latest) {
            return ("Latest log: {0} ({1:yyyy-MM-dd HH:mm})" -f $latest.Name, $latest.LastWriteTime)
        }
        return "data\logs exists, no files"
    }
    catch {
        return "Log scan unavailable"
    }
}

function Get-LineRuntimeText {
    param([string]$Root)
    $items = [System.Collections.Generic.List[string]]::new()
    $owner = Join-Path $Root "data\handoff\worker_owner.json"
    $notice = Join-Path $Root "data\material_ingest\latest_notice.json"
    $items.Add("LINE owner: $(Test-PathText $owner)")
    $items.Add("Material notice: $(Test-PathText $notice)")
    return ($items -join " | ")
}

function Get-ProjectReport {
    $report = [System.Collections.Generic.List[string]]::new()
    $report.Add(("Z13 Daily Launch Monitor - {0:yyyy-MM-dd HH:mm:ss}" -f (Get-Date)))
    $report.Add("")
    foreach ($project in $Projects.Values) {
        $root = $project.Root
        $runbook = Join-Path $root $project.Runbook
        $launcher = Join-Path $root $project.Launcher
        $venv = Join-Path $root ".venv\Scripts\python.exe"
        $envFile = Join-Path $root ".env"
        $automation = Join-Path $root "automations"

        $report.Add("[$($project.Name)]")
        $report.Add("Root:     $(Test-PathText $root)  $root")
        $report.Add("Launcher: $(Test-PathText $launcher)  $($project.Launcher)")
        $report.Add("Runbook:  $(Test-PathText $runbook)  $($project.Runbook)")
        $report.Add("Python:   $(Test-PathText $venv)  .venv\Scripts\python.exe")
        $report.Add("Env:      $(Test-PathText $envFile)  .env")
        $report.Add("Automations: $(Test-PathText $automation)")
        if ($project.Name -eq "LINE") {
            $report.Add((Get-LineRuntimeText -Root $root))
        }
        $report.Add((Get-LatestLogText -Root $root))
        $report.Add("Git:      $(Get-GitSummary -Root $root)")
        $report.Add("")
    }
    return ($report -join [Environment]::NewLine)
}

function Refresh-Monitor {
    try {
        $script:MonitorBox.Text = Get-ProjectReport
        $script:StatusLabel.Text = "Monitor refreshed."
    }
    catch {
        $script:MonitorBox.Text = "Monitor failed: $($_.Exception.Message)"
        $script:StatusLabel.Text = "Monitor failed."
    }
}

function New-Button {
    param(
        [string]$Text,
        [System.Drawing.Color]$Color,
        [scriptblock]$Click
    )
    $button = [System.Windows.Forms.Button]::new()
    $button.Width = 214
    $button.Height = 58
    $button.Margin = [System.Windows.Forms.Padding]::new(6)
    $button.Padding = [System.Windows.Forms.Padding]::new(8, 4, 8, 4)
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderSize = 1
    $button.BackColor = $Color
    $button.ForeColor = [System.Drawing.Color]::White
    $button.Font = [System.Drawing.Font]::new("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $button.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $button.Text = $Text
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    $button.Add_Click($Click)
    return $button
}

function New-Section {
    param(
        [string]$Title,
        [int]$Height
    )
    $panel = [System.Windows.Forms.Panel]::new()
    $panel.Width = 705
    $panel.Height = $Height
    $panel.Margin = [System.Windows.Forms.Padding]::new(0, 0, 0, 14)
    $panel.BackColor = [System.Drawing.Color]::White
    $panel.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle

    $heading = [System.Windows.Forms.Label]::new()
    $heading.Location = [System.Drawing.Point]::new(0, 0)
    $heading.Size = [System.Drawing.Size]::new(703, 34)
    $heading.Padding = [System.Windows.Forms.Padding]::new(12, 8, 0, 0)
    $heading.BackColor = [System.Drawing.Color]::FromArgb(238, 241, 244)
    $heading.ForeColor = [System.Drawing.Color]::FromArgb(31, 41, 55)
    $heading.Font = [System.Drawing.Font]::new("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $heading.Text = $Title

    $flow = [System.Windows.Forms.FlowLayoutPanel]::new()
    $flow.Location = [System.Drawing.Point]::new(8, 42)
    $flow.Size = [System.Drawing.Size]::new(688, $Height - 48)
    $flow.WrapContents = $true
    $flow.AutoScroll = $false
    $flow.BackColor = [System.Drawing.Color]::White

    $panel.Controls.Add($flow)
    $panel.Controls.Add($heading)
    return [pscustomobject]@{ Panel = $panel; Flow = $flow }
}

function Get-DescendantControls {
    param([System.Windows.Forms.Control]$Control)
    foreach ($child in $Control.Controls) {
        $child
        foreach ($descendant in Get-DescendantControls -Control $child) {
            $descendant
        }
    }
}

$form = [System.Windows.Forms.Form]::new()
$form.Text = "Z13 Daily Launch Menu"
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.Size = [System.Drawing.Size]::new(1250, 820)
$form.MinimumSize = [System.Drawing.Size]::new(1080, 720)
$form.BackColor = [System.Drawing.Color]::FromArgb(245, 247, 250)
$form.Font = [System.Drawing.Font]::new("Segoe UI", 9)

$header = [System.Windows.Forms.Panel]::new()
$header.Dock = [System.Windows.Forms.DockStyle]::Top
$header.Height = 82
$header.BackColor = [System.Drawing.Color]::FromArgb(32, 47, 65)

$title = [System.Windows.Forms.Label]::new()
$title.AutoSize = $true
$title.Location = [System.Drawing.Point]::new(24, 14)
$title.ForeColor = [System.Drawing.Color]::White
$title.Font = [System.Drawing.Font]::new("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
$title.Text = "Z13 Daily Launch Menu"
$header.Controls.Add($title)

$subtitle = [System.Windows.Forms.Label]::new()
$subtitle.AutoSize = $true
$subtitle.Location = [System.Drawing.Point]::new(28, 52)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(218, 226, 235)
$subtitle.Text = "ARM + CRM + LINE + EasyFlow daily consoles, read-only checks, runbooks, and local co-work monitor."
$header.Controls.Add($subtitle)

$statusStrip = [System.Windows.Forms.StatusStrip]::new()
$script:StatusLabel = [System.Windows.Forms.ToolStripStatusLabel]::new()
$script:StatusLabel.Spring = $true
$script:StatusLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$script:StatusLabel.Text = "Ready. Use Monitor Refresh first, then open the project console you need."
$statusStrip.Items.Add($script:StatusLabel) | Out-Null

$main = [System.Windows.Forms.TableLayoutPanel]::new()
$main.Dock = [System.Windows.Forms.DockStyle]::Fill
$main.ColumnCount = 2
$main.RowCount = 1
$main.Padding = [System.Windows.Forms.Padding]::new(18, 16, 18, 12)
$main.BackColor = $form.BackColor
$main.ColumnStyles.Add([System.Windows.Forms.ColumnStyle]::new([System.Windows.Forms.SizeType]::Absolute, 730)) | Out-Null
$main.ColumnStyles.Add([System.Windows.Forms.ColumnStyle]::new([System.Windows.Forms.SizeType]::Percent, 100)) | Out-Null

$left = [System.Windows.Forms.FlowLayoutPanel]::new()
$left.Dock = [System.Windows.Forms.DockStyle]::Fill
$left.FlowDirection = [System.Windows.Forms.FlowDirection]::TopDown
$left.WrapContents = $false
$left.AutoScroll = $true
$left.BackColor = $form.BackColor

$right = [System.Windows.Forms.Panel]::new()
$right.Dock = [System.Windows.Forms.DockStyle]::Fill
$right.BackColor = [System.Drawing.Color]::White
$right.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle

$monitorHeader = [System.Windows.Forms.Panel]::new()
$monitorHeader.Dock = [System.Windows.Forms.DockStyle]::Top
$monitorHeader.Height = 46
$monitorHeader.BackColor = [System.Drawing.Color]::FromArgb(238, 241, 244)

$monitorTitle = [System.Windows.Forms.Label]::new()
$monitorTitle.AutoSize = $true
$monitorTitle.Location = [System.Drawing.Point]::new(12, 13)
$monitorTitle.ForeColor = [System.Drawing.Color]::FromArgb(31, 41, 55)
$monitorTitle.Font = [System.Drawing.Font]::new("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$monitorTitle.Text = "Co-work Monitor"
$monitorHeader.Controls.Add($monitorTitle)

$refreshButton = New-Button "Refresh Monitor" ([System.Drawing.Color]::FromArgb(82, 92, 105)) { Refresh-Monitor }
$refreshButton.Width = 144
$refreshButton.Height = 32
$refreshButton.Location = [System.Drawing.Point]::new(290, 7)
$refreshButton.Margin = [System.Windows.Forms.Padding]::new(0)
$monitorHeader.Controls.Add($refreshButton)

$script:MonitorBox = [System.Windows.Forms.TextBox]::new()
$script:MonitorBox.Dock = [System.Windows.Forms.DockStyle]::Fill
$script:MonitorBox.Multiline = $true
$script:MonitorBox.ScrollBars = [System.Windows.Forms.ScrollBars]::Both
$script:MonitorBox.ReadOnly = $true
$script:MonitorBox.WordWrap = $false
$script:MonitorBox.Font = [System.Drawing.Font]::new("Consolas", 9)
$script:MonitorBox.BackColor = [System.Drawing.Color]::White
$script:MonitorBox.ForeColor = [System.Drawing.Color]::FromArgb(31, 41, 55)
$right.Controls.Add($script:MonitorBox)
$right.Controls.Add($monitorHeader)

$consoleSection = New-Section "1. Open Existing Operator Consoles" 176
foreach ($project in $Projects.Values) {
    $p = $project
    $consoleSection.Flow.Controls.Add((New-Button "$($p.Name)`r`nConsole" $p.Accent { Start-ProjectLauncher -Project $p }.GetNewClosure()))
}
$left.Controls.Add($consoleSection.Panel)

$checkSection = New-Section "2. Run Read-Only Daily Checks" 176
foreach ($project in $Projects.Values) {
    $p = $project
    $checkSection.Flow.Controls.Add((New-Button "$($p.Name)`r`nSafe Checks" ([System.Drawing.Color]::FromArgb(40, 120, 165)) { Start-SequentialChecks -Project $p }.GetNewClosure()))
}
$left.Controls.Add($checkSection.Panel)

$runbookSection = New-Section "3. Open Written Runbooks" 176
foreach ($project in $Projects.Values) {
    $p = $project
    $runbookSection.Flow.Controls.Add((New-Button "$($p.Name)`r`nRunbook" ([System.Drawing.Color]::FromArgb(95, 85, 145)) { Open-ProjectRunbook -Project $p }.GetNewClosure()))
}
$left.Controls.Add($runbookSection.Panel)

$folderSection = New-Section "4. Open Project Folders" 176
foreach ($project in $Projects.Values) {
    $p = $project
    $folderSection.Flow.Controls.Add((New-Button "$($p.Name)`r`nFolder" ([System.Drawing.Color]::FromArgb(88, 98, 108)) { Open-ProjectFolder -Project $p }.GetNewClosure()))
}
$left.Controls.Add($folderSection.Panel)

$main.Controls.Add($left, 0, 0)
$main.Controls.Add($right, 1, 0)

$form.Controls.Add($main)
$form.Controls.Add($statusStrip)
$form.Controls.Add($header)
$header.BringToFront()
$statusStrip.BringToFront()

if ($ValidateLayout) {
    $form.CreateControl()
    $form.PerformLayout()
    Refresh-Monitor
    $buttons = @(Get-DescendantControls -Control $form | Where-Object { $_ -is [System.Windows.Forms.Button] })
    if ($buttons.Count -lt 17) {
        throw "Expected launcher buttons were not created."
    }
    Write-Host "Z13 launch menu layout validation passed."
    Write-Host "Buttons: $($buttons.Count)"
    Write-Host "Projects: $($Projects.Count)"
    exit 0
}

Refresh-Monitor
[void]$form.ShowDialog()
