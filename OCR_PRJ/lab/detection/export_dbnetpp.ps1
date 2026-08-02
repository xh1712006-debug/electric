<#!
.SYNOPSIS
Exports the downloaded DBNet++ ResNet-50 training checkpoint to Paddle inference files.

.DESCRIPTION
The checkpoint in downloads/det_r50_db++_icdar15_train contains parameters only.
PaddleOCR's export tool combines those parameters with the matching architecture
configuration and writes an inference model to models/dbnetpp_resnet50.

Run this with a Python environment compatible with the supplied PaddleOCR 2.x
checkout. Keep that export environment separate from the PaddleOCR 3.x runtime
used by run_comparison.py.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PaddleOcrRoot,

    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$paddleRoot = (Resolve-Path $PaddleOcrRoot).Path
$pythonCommand = if (Test-Path $Python) { (Resolve-Path $Python).Path } else { $Python }
$checkpoint = Join-Path $projectRoot "lab\detection\downloads\det_r50_db++_icdar15_train\best_accuracy"
$config = Join-Path $paddleRoot "configs\det\det_r50_db++_icdar15.yml"
$output = Join-Path $projectRoot "lab\detection\models\dbnetpp_resnet50"

if (-not (Test-Path "$checkpoint.pdparams")) {
    throw "DBNet++ checkpoint was not found: $checkpoint.pdparams"
}
if (-not (Test-Path $config)) {
    throw "Matching config was not found: $config. Use a PaddleOCR checkout that contains configs/det/det_r50_db++_icdar15.yml."
}
if (Test-Path $output) {
    $existing = Get-ChildItem -LiteralPath $output -Force
    if ($existing.Count -gt 0) {
        throw "Refusing to overwrite existing inference files in $output. Move them aside first if you intentionally want to re-export."
    }
} else {
    New-Item -ItemType Directory -Path $output | Out-Null
}

Push-Location $paddleRoot
try {
    & $pythonCommand "tools\export_model.py" "-c" $config "-o" "Global.pretrained_model=$checkpoint" "Global.save_inference_dir=$output"
    if ($LASTEXITCODE -ne 0) {
        throw "PaddleOCR export failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$expected = @("inference.pdmodel", "inference.pdiparams", "inference.json")
$found = $expected | Where-Object { Test-Path (Join-Path $output $_) }
if ($found.Count -eq 0) {
    throw "Export completed but no recognised inference model file was written to $output."
}

Write-Host "DBNet++ inference model exported to: $output"
