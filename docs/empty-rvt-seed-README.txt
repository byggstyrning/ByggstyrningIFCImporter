empty_R{RevitYear}.rvt (BatchRvt host document)

============================================================



Phase 1a (Graphisoft-style main IFC import) runs under Revit Batch Processor,

which requires a valid .RVT in the file list before the task script runs.
    10|


Default path when -RbpSeedRvt is not set:



  demo\in\empty_R2025.rvt   — use with -RevitYear 2025 (Revit 2025 host file)

  demo\in\empty_R2026.rvt   — use with -RevitYear 2026 (Revit 2026 host file)


    20|
Create each file in the matching Revit version:

  File > New > Metric template (any minimal project) > Save As

  Save as:  demo\in\empty_R2025.rvt  (or empty_R2026.rvt) alongside the demo IFC inputs



Override only when necessary with -RbpSeedRvt on powershell\Run-ByggPipelineSetup.ps1

or set BYGG_RBP_SEED_RVT if the seed lives outside demo\in.


    30|
See docs\README-pipeline.txt for the full end-to-end command and prerequisites.



The seed is only a host; the imported model is written to BYGG_IFC_OUTPUT_PATH (same

as the main architecture .RVT path derived from your .IFC).

