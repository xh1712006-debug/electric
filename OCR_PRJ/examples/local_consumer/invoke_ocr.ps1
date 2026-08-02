[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPdf,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [Parameter(Mandatory = $true)][string]$CorrelationId,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$previousPythonPath = $env:PYTHONPATH
$stderrPath = [System.IO.Path]::GetTempFileName()

function Write-ConsumerSummary {
    param([hashtable]$Summary, [int]$ExitCode)
    [Console]::Out.WriteLine(($Summary | ConvertTo-Json -Compress -Depth 8))
    exit $ExitCode
}

function Resolve-PublicArtifact {
    param([string]$Root, [string]$RelativePath)
    if ([System.IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains("\")) {
        throw "artifact_path_not_relative"
    }
    $parts = $RelativePath.Split("/")
    if ($parts.Count -eq 0 -or ($parts | Where-Object { $_ -in @("", ".", "..") })) {
        throw "artifact_path_not_relative"
    }
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd("\", "/")
    $candidate = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($resolvedRoot, ($parts -join [System.IO.Path]::DirectorySeparatorChar)))
    if (-not $candidate.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "artifact_path_outside_output_root"
    }
    return $candidate
}

try {
    $resolvedProject = [System.IO.Path]::GetFullPath($ProjectRoot)
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedProject "src\relay_form_ocr") -PathType Container)) {
        throw "public_module_root_missing"
    }
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $resolvedProject
    } else {
        $resolvedProject + [System.IO.Path]::PathSeparator + $previousPythonPath
    }
    $arguments = @(
        "-m", "src.relay_form_ocr",
        "--input", [System.IO.Path]::GetFullPath($InputPdf),
        "--output-root", [System.IO.Path]::GetFullPath($OutputRoot),
        "--correlation-id", $CorrelationId,
        "--json"
    )
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $stdoutLines = @(& $PythonExe @arguments 2> $stderrPath)
    $ErrorActionPreference = $savedErrorActionPreference
    $ocrExitCode = $LASTEXITCODE
    $stdoutText = $stdoutLines -join "`n"
    if ([string]::IsNullOrWhiteSpace($stdoutText)) {
        throw "cli_stdout_missing"
    }
    $result = $stdoutText | ConvertFrom-Json
    foreach ($required in @("schema_version", "pipeline_version", "correlation_id", "status", "review_status", "artifact_manifest")) {
        if ($null -eq $result.PSObject.Properties[$required]) {
            throw "result_contract_invalid"
        }
    }

    $artifacts = @($result.artifact_manifest.artifacts)
    $verified = 0
    foreach ($artifact in $artifacts) {
        $artifactPath = Resolve-PublicArtifact -Root $OutputRoot -RelativePath ([string]$artifact.relative_path)
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw "artifact_missing_or_not_regular"
        }
        $file = Get-Item -LiteralPath $artifactPath
        if ($file.Length -ne [long]$artifact.size_bytes) {
            throw "artifact_size_mismatch"
        }
        $hash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne [string]$artifact.sha256) {
            throw "artifact_checksum_mismatch"
        }
        $verified += 1
    }

    $manifestArtifacts = @($artifacts | Where-Object { $_.kind -eq "artifact_manifest" })
    $manifestAvailable = $manifestArtifacts.Count -eq 1
    $sourceUnchanged = $null
    if ($artifacts.Count -gt 0) {
        if (-not $manifestAvailable) {
            throw "physical_manifest_count_invalid"
        }
        $manifestPath = Resolve-PublicArtifact -Root $OutputRoot -RelativePath ([string]$manifestArtifacts[0].relative_path)
        $physicalManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
        if ([string]$physicalManifest.workspace_id -ne [string]$result.artifact_manifest.workspace_id) {
            throw "physical_manifest_workspace_mismatch"
        }
        $expectedStatus = if ($result.status -eq "failed") { "failed" } else { "completed" }
        if ([string]$physicalManifest.status -ne $expectedStatus) {
            throw "physical_manifest_status_mismatch"
        }
        $sourceUnchanged = $physicalManifest.source.unchanged
        if ($sourceUnchanged -ne $true) {
            throw "source_immutability_not_confirmed"
        }
    }

    if ($result.status -eq "failed") {
        $outcome = "failed"
        $consumerExit = 20
    } elseif ($result.review_status -eq "review_required") {
        $outcome = "manual_review_required"
        $consumerExit = 10
    } else {
        $outcome = "ready_for_use"
        $consumerExit = 0
    }
    $publicError = $null
    if ($null -ne $result.error) {
        $publicError = @{
            code = [string]$result.error.code
            stage = [string]$result.error.stage
            retryable = [bool]$result.error.retryable
        }
    }
    Write-ConsumerSummary -ExitCode $consumerExit -Summary @{
        consumer_schema_version = "1.0"
        correlation_id = [string]$result.correlation_id
        schema_version = [string]$result.schema_version
        pipeline_version = [string]$result.pipeline_version
        outcome = $outcome
        processing_status = [string]$result.status
        review_status = [string]$result.review_status
        page_count = if ($null -ne $result.document) { [int]$result.document.page_count } else { @($result.pages).Count }
        warning_count = @($result.warnings).Count
        artifact_count = $artifacts.Count
        manifest_audit = @{
            available = $manifestAvailable
            source_unchanged = $sourceUnchanged
            verified_artifact_count = $verified
            all_verified = $true
        }
        public_error = $publicError
        consumer_error = $null
        cli_exit_code = $ocrExitCode
    }
} catch {
    Write-ConsumerSummary -ExitCode 21 -Summary @{
        consumer_schema_version = "1.0"
        correlation_id = $CorrelationId
        outcome = "consumer_failure"
        consumer_error = "consumer_platform_error"
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    if (Test-Path -LiteralPath $stderrPath) {
        Remove-Item -LiteralPath $stderrPath -Force
    }
}
