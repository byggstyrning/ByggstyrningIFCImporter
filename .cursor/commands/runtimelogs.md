# Command: Show runtime log contents for troubleshooting

```powershell
# pyRevit runtime logs: %APPDATA%\pyRevit\<RevitYear>\pyRevit_*_runtime.log
$LOG_PATTERN = "pyRevit_*_runtime.log"
$PYREVIT_BASE = Join-Path $env:APPDATA "pyRevit"

function Get-PyRevitVersionDirectories {
    if (-not (Test-Path $PYREVIT_BASE)) { return @() }
    Get-ChildItem -Path $PYREVIT_BASE -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}$' } |
        Sort-Object { [int]$_.Name } -Descending
}

function Find-LatestLogFile {
    <#
    .SYNOPSIS
    Find the most recent pyRevit runtime log file.
    
    .PARAMETER LogDir
    Directory to search. If empty, searches all Revit year folders under %APPDATA%\pyRevit
    
    .PARAMETER Pattern
    File pattern to match (default: $LOG_PATTERN)
    
    .OUTPUTS
    System.String. Path to most recent log file, or $null if not found
    #>
    param(
        [string]$LogDir = $null,
        [string]$Pattern = $LOG_PATTERN
    )
    $dirs = @()
    if ($LogDir -and (Test-Path $LogDir)) {
        $dirs = @($LogDir)
    } else {
        $dirs = @(Get-PyRevitVersionDirectories | ForEach-Object { $_.FullName })
    }
    if ($dirs.Count -eq 0) { return $null }
    $all = @()
    foreach ($d in $dirs) {
        $all += Get-ChildItem -Path $d -Filter $Pattern -ErrorAction SilentlyContinue
    }
    if ($null -eq $all -or $all.Count -eq 0) { return $null }
    $latest = $all | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    return $latest.FullName
}

function Read-LogFile {
    <#
    .SYNOPSIS
    Read pyRevit runtime log file.
    
    .PARAMETER FilePath
    Path to log file
    
    .PARAMETER Lines
    Number of recent lines to show (default: all)
    
    .PARAMETER FilterLevel
    Filter by log level ('ERROR', 'WARNING', 'INFO', 'DEBUG', $null = all)
    
    .OUTPUTS
    PSCustomObject with LogLines and FileStats properties
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,
        
        [int]$Lines = 0,
        
        [string]$FilterLevel = $null
    )
    
    if (-not (Test-Path $FilePath)) {
        return @{
            LogLines = $null
            FileStats = @{ Error = "Log file not found: $FilePath" }
        }
    }
    
    try {
        $fileInfo = Get-Item $FilePath
        $fileStats = @{
            Path = $FilePath
            Size = $fileInfo.Length
            Modified = $fileInfo.LastWriteTime
            Exists = $true
        }
        
        # Read log file
        $allLines = Get-Content -Path $FilePath -Encoding UTF8 -ErrorAction Stop
        
        # Filter by log level if specified
        if ($FilterLevel) {
            $allLines = $allLines | Where-Object { $_ -match $FilterLevel }
        }
        
        # Get recent lines if specified
        if ($Lines -gt 0) {
            $logLines = $allLines | Select-Object -Last $Lines
        } else {
            $logLines = $allLines
        }
        
        $fileStats.TotalLines = $allLines.Count
        $fileStats.DisplayedLines = $logLines.Count
        
        return @{
            LogLines = $logLines
            FileStats = $fileStats
        }
    }
    catch {
        return @{
            LogLines = $null
            FileStats = @{ Error = "Error reading log file: $($_.Exception.Message)" }
        }
    }
}

function Format-LogOutput {
    <#
    .SYNOPSIS
    Format log output for display.
    #>
    param(
        [array]$LogLines,
        [hashtable]$FileStats
    )
    
    $output = @()
    
    # Header
    $output += "=" * 80
    $output += "pyRevit Runtime Log Viewer"
    $output += "=" * 80
    
    if ($FileStats.Error) {
        $output += ""
        $output += "ERROR: $($FileStats.Error)"
        return $output -join "`n"
    }
    
    # File stats
    $output += ""
    $output += "File: $($FileStats.Path)"
    $output += "Size: $([math]::Round($FileStats.Size / 1KB, 2)) KB"
    $output += "Last Modified: $($FileStats.Modified.ToString('yyyy-MM-dd HH:mm:ss'))"
    $output += "Total Lines: $($FileStats.TotalLines)"
    $output += "Displayed Lines: $($FileStats.DisplayedLines)"
    
    # Log content
    $output += ""
    $output += "-" * 80
    $output += "LOG CONTENT:"
    $output += "-" * 80
    $output += ""
    
    if ($LogLines -and $LogLines.Count -gt 0) {
        $startLine = $FileStats.TotalLines - $FileStats.DisplayedLines + 1
        for ($i = 0; $i -lt $LogLines.Count; $i++) {
            $lineNum = $startLine + $i
            $line = $LogLines[$i]
            $lineStripped = $line.TrimEnd()
            
            # Highlight errors and warnings
            if ($lineStripped -match "ERROR") {
                $output += "[$lineNum] ERROR: $lineStripped"
            }
            elseif ($lineStripped -match "WARNING|WARN") {
                $output += "[$lineNum] WARNING: $lineStripped"
            }
            else {
                $output += "[$lineNum] $lineStripped"
            }
        }
    } else {
        $output += "(No log entries found)"
    }
    
    $output += ""
    $output += "=" * 80
    
    return $output -join "`n"
}

function Show-RecentErrors {
    <#
    .SYNOPSIS
    Show recent ERROR entries.
    #>
    param([int]$Lines = 100)
    
    $result = Read-LogFile -FilePath $script:LOG_PATH -Lines $Lines -FilterLevel "ERROR"
    Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
}

function Show-RecentWarnings {
    <#
    .SYNOPSIS
    Show recent WARNING entries.
    #>
    param([int]$Lines = 100)
    
    $result = Read-LogFile -FilePath $script:LOG_PATH -Lines $Lines -FilterLevel "WARNING"
    Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
}

function Show-RecentLogs {
    <#
    .SYNOPSIS
    Show recent log entries (all levels).
    #>
    param([int]$Lines = 100)
    
    $result = Read-LogFile -FilePath $script:LOG_PATH -Lines $Lines
    Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
}

function Show-AllLogs {
    <#
    .SYNOPSIS
    Show all log entries.
    #>
    $result = Read-LogFile -FilePath $script:LOG_PATH
    Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
}

function Search-Logs {
    <#
    .SYNOPSIS
    Search log entries for a specific term.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$SearchTerm,
        
        [int]$Lines = 0
    )
    
    $result = Read-LogFile -FilePath $script:LOG_PATH -Lines $Lines
    
    if ($result.LogLines -and $result.LogLines.Count -gt 0) {
        $matchingLines = @()
        $startLine = $result.FileStats.TotalLines - $result.LogLines.Count + 1
        
        for ($i = 0; $i -lt $result.LogLines.Count; $i++) {
            $line = $result.LogLines[$i]
            if ($line -match [regex]::Escape($SearchTerm)) {
                $lineNum = $startLine + $i
                $matchingLines += [PSCustomObject]@{
                    LineNumber = $lineNum
                    Line = $line
                }
            }
        }
        
        if ($matchingLines.Count -gt 0) {
            $output = @()
            $output += "=" * 80
            $output += "Search Results for: '$SearchTerm'"
            $output += "=" * 80
            $output += "Found $($matchingLines.Count) matches:"
            $output += ""
            foreach ($match in $matchingLines) {
                $output += "[$($match.LineNumber)] $($match.Line.TrimEnd())"
            }
            $output -join "`n" | Write-Host
        } else {
            Write-Host "No matches found for '$SearchTerm'"
        }
    } else {
        Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
    }
}

function List-AllLogFiles {
    <#
    .SYNOPSIS
    List all available pyRevit runtime log files with details (all Revit year folders).
    #>
    $pattern = $LOG_PATTERN
    if (-not (Test-Path $PYREVIT_BASE)) {
        Write-Host "No pyRevit folder under: $PYREVIT_BASE"
        return
    }
    $logFiles = @()
    foreach ($verDir in Get-PyRevitVersionDirectories) {
        $logFiles += Get-ChildItem -Path $verDir.FullName -Filter $pattern -ErrorAction SilentlyContinue
    }
    if ($null -eq $logFiles -or $logFiles.Count -eq 0) {
        Write-Host "No log files found under $PYREVIT_BASE matching: $pattern"
        return
    }
    $logFiles = $logFiles | Sort-Object LastWriteTime -Descending
    Write-Host ("=" * 80)
    Write-Host "Available pyRevit Runtime Log Files"
    Write-Host ("=" * 80)
    Write-Host ""
    Write-Host "Base: $PYREVIT_BASE (all Revit year folders)"
    Write-Host "Pattern: $pattern"
    Write-Host ""
    
    $index = 1
    foreach ($logFile in $logFiles) {
        $isCurrent = ($logFile.FullName -eq $script:LOG_PATH)
        $marker = if ($isCurrent) { " <-- CURRENT" } else { "" }
        
        Write-Host "[$index] $($logFile.Name)"
        Write-Host "     Path: $($logFile.FullName)$marker"
        Write-Host "     Size: $([math]::Round($logFile.Length / 1KB, 2)) KB"
        Write-Host "     Modified: $($logFile.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
        Write-Host ""
        $index++
    }
}

function Show-LogFileInfo {
    <#
    .SYNOPSIS
    Show information about the currently selected log file.
    #>
    if (-not $script:LOG_PATH) {
        Write-Host "ERROR: No log file found. Check if pyRevit log directory exists."
        Write-Host "Expected directory: $PYREVIT_LOG_DIR"
        return
    }
    
    if (-not (Test-Path $script:LOG_PATH)) {
        Write-Host "ERROR: Log file not found: $script:LOG_PATH"
        return
    }
    
    $fileInfo = Get-Item $script:LOG_PATH
    
    Write-Host ("=" * 80)
    Write-Host "Current Log File Information"
    Write-Host ("=" * 80)
    Write-Host ""
    Write-Host "File: $($fileInfo.FullName)"
    Write-Host "Size: $([math]::Round($fileInfo.Length / 1KB, 2)) KB ($($fileInfo.Length.ToString('N0')) bytes)"
    Write-Host "Created: $($fileInfo.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host "Last Modified: $($fileInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
    
    # Count lines
    try {
        $lineCount = (Get-Content -Path $script:LOG_PATH -ErrorAction Stop).Count
        Write-Host "Total Lines: $($lineCount.ToString('N0'))"
    }
    catch {
        Write-Host "Error counting lines: $($_.Exception.Message)"
    }
    
    Write-Host ""
}

function Show-StartupTrace {
    <#
    .SYNOPSIS
    Show log lines that mention extension loading, startup, ribbon, or this extension.
    #>
    param([int]$Lines = 200)
    if (-not $script:LOG_PATH) {
        Write-Host "ERROR: No log file selected. Run Find-LatestLogFile first."
        return
    }
    $tail = [Math]::Max($Lines * 3, 3000)
    $chunk = Get-Content -Path $script:LOG_PATH -Tail $tail -Encoding UTF8
    $regex = [regex]'(?i)(startup|extension|pybyggstyrning|nobeldca|nobel|pyrevit|bundle|ribbon|idling|startup\.py|_runtime|traceback|exception|xaml|parse)'
    $filtered = $chunk | Where-Object { $regex.IsMatch($_) }
    Write-Host ("=" * 80)
    Write-Host "Startup / extension trace (last $Lines matching lines)"
    Write-Host ("=" * 80)
    Write-Host "File: $script:LOG_PATH"
    Write-Host ""
    $filtered | Select-Object -Last $Lines | ForEach-Object { Write-Host $_ }
    Write-Host ""
}

# Auto-detect most recent log file across all Revit versions
$script:LOG_PATH = Find-LatestLogFile
$PYREVIT_LOG_DIR = if ($script:LOG_PATH) { Split-Path $script:LOG_PATH -Parent } else { Join-Path $PYREVIT_BASE "2025" }

# Main execution - show recent logs by default
if ($MyInvocation.InvocationName -ne '.') {
    # Check if log file was found
    if (-not $script:LOG_PATH) {
        Write-Host "ERROR: Could not find pyRevit runtime log file."
        Write-Host "Searched under: $PYREVIT_BASE"
        Write-Host "Pattern: $LOG_PATTERN"
        Write-Host ""
        Write-Host "Trying to list available log files..."
        List-AllLogFiles
    } else {
        # Default: show last 100 lines
        Show-RecentLogs -Lines 100
    }
}
```

## Usage Examples

### Show recent log entries (default)
```powershell
Show-RecentLogs -Lines 100
```

### Show only errors
```powershell
Show-RecentErrors -Lines 50
```

### Show only warnings
```powershell
Show-RecentWarnings -Lines 50
```

### Show all logs
```powershell
Show-AllLogs
```

### Search for specific term
```powershell
Search-Logs -SearchTerm "ColorElements" -Lines 500
```

### Custom filtering
```powershell
$result = Read-LogFile -FilePath $LOG_PATH -Lines 200 -FilterLevel "ERROR"
Format-LogOutput -LogLines $result.LogLines -FileStats $result.FileStats | Write-Host
```

## Debugging Utilities

### List all available log files
```powershell
List-AllLogFiles
```
Shows all pyRevit runtime log files with their sizes and modification times.

### Show current log file info
```powershell
Show-LogFileInfo
```
Displays detailed information about the currently selected log file.

### Find latest log file manually
```powershell
$latestLog = Find-LatestLogFile
Write-Host "Latest log: $latestLog"
```

### Startup / extension / ribbon trace (filtered tail)
```powershell
Show-StartupTrace -Lines 200
```

## PowerShell One-Liners

### Quick view of latest log (last 50 lines, any Revit year)
```powershell
$log = Get-ChildItem "$env:APPDATA\pyRevit\*\pyRevit_*_runtime.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $log.FullName -Tail 50
```

### Find all errors in latest log
```powershell
$log = Get-ChildItem "$env:APPDATA\pyRevit\*\pyRevit_*_runtime.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $log.FullName | Select-String "ERROR"
```

### Count errors in latest log
```powershell
$log = Get-ChildItem "$env:APPDATA\pyRevit\*\pyRevit_*_runtime.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
(Get-Content $log.FullName | Select-String "ERROR").Count
```

## Notes

- **Auto-detection**: The script finds the most recent `pyRevit_*_runtime.log` under **any** `%APPDATA%\pyRevit\20xx` folder
- **Override directory**: Pass a folder to `Find-LatestLogFile -LogDir "C:\path\to\pyRevit\2025"` if needed
- **Pattern matching**: Change `$LOG_PATTERN` to match different log file naming conventions
- Default behavior shows the last 100 lines of all log entries
- Use `-FilterLevel` parameter to filter by log level (ERROR, WARNING, INFO, DEBUG)
- File encoding is UTF-8
- Line numbers are shown for easy reference
- Errors and warnings are highlighted in the output

## Troubleshooting

If the script can't find log files:
1. Check that `$PYREVIT_LOG_DIR` points to the correct directory
2. Verify the log file pattern matches your pyRevit version
3. Run `List-AllLogFiles` to see what files are available
4. Manually set `$LOG_PATH` if auto-detection fails
5. Use `$env:APPDATA` instead of hardcoded path for portability:
   ```powershell
   $PYREVIT_LOG_DIR = "$env:APPDATA\pyRevit\2025"
   ```
