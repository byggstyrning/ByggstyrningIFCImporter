<#
.SYNOPSIS
    Runs Graphisoft IFC import on the demo rooms IFC only, writing demo\out\roomsdemo.rvt.

.DESCRIPTION
    Thin wrapper around Run-ByggPipelineSetup.ps1 -ImportRoomsIfcOnly. Same BatchRvt path as the
    full pipeline Phase 1b. Pass through any extra arguments (e.g. -RoomsIfcPath, -RoomsModelPath, -RbpSeedRvt).

.EXAMPLE
    .\Run-RoomsImportDemo.ps1
.EXAMPLE
    # Headless xBIM native rooms (no Graphisoft)
    .\Run-ByggPipelineSetup.ps1 -ImportRoomsIfcOnly -RoomsImporter Xbim
.EXAMPLE
    .\Run-RoomsImportDemo.ps1 -RoomsModelPath "C:\temp\my_rooms.rvt"
#>
& (Join-Path $PSScriptRoot "Run-ByggPipelineSetup.ps1") -ImportRoomsIfcOnly @args
