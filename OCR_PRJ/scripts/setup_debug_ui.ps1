[CmdletBinding()]
param(
    [string]$VenvPath = ".venv",
    [string]$PythonCommand = "python",
    [switch]$SkipInstall,
    [switch]$SkipModelWarmup,
    [switch]$RecreateVenv,
    [switch]$Run
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )
    Write-Host "`n==> $Description" -ForegroundColor Cyan
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repoRoot

    if ([System.IO.Path]::IsPathRooted($VenvPath)) {
        $resolvedVenv = [System.IO.Path]::GetFullPath($VenvPath)
    } else {
        $resolvedVenv = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $VenvPath))
    }
    $venvPython = Join-Path $resolvedVenv "Scripts\python.exe"

    if ($RecreateVenv -and (Test-Path -LiteralPath $resolvedVenv)) {
        $repoPrefix = $repoRoot.TrimEnd('\') + '\'
        $isInsideRepository = $resolvedVenv.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)
        if (-not $isInsideRepository -or $resolvedVenv -eq $repoRoot) {
            throw "Refusing to recreate an unsafe environment path: $resolvedVenv"
        }
        Write-Host "`n==> Removing the requested virtual environment: $resolvedVenv" -ForegroundColor Yellow
        Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (Test-Path -LiteralPath $resolvedVenv) {
            throw "The environment directory exists but has no Scripts\python.exe: $resolvedVenv. Remove/rename it or choose another -VenvPath."
        }
        $basePython = Get-Command $PythonCommand -ErrorAction SilentlyContinue
        if ($null -eq $basePython) {
            throw "Python was not found as '$PythonCommand'. Install 64-bit Python 3.10-3.12 or pass -PythonCommand with its path."
        }
        Invoke-Checked -Executable $basePython.Source -Arguments @(
            "-c",
            "import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 12), 'Python 3.10-3.12 is required; found ' + sys.version.split()[0]"
        ) -Description "Checking the base Python version"
        Invoke-Checked -Executable $basePython.Source -Arguments @("-m", "venv", $resolvedVenv) -Description "Creating $resolvedVenv"
    }

    Invoke-Checked -Executable $venvPython -Arguments @(
        "-c",
        "import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 12), 'Python 3.10-3.12 is required; found ' + sys.version.split()[0]"
    ) -Description "Checking the virtual environment"

    if (-not $SkipInstall) {
        Invoke-Checked -Executable $venvPython -Arguments @(
            "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools<81"
        ) -Description "Updating Python packaging tools"
        Invoke-Checked -Executable $venvPython -Arguments @(
            "-m", "pip", "install", "-r", "src\debug_ui\requirements-full.txt"
        ) -Description "Installing the complete OCR/debug UI runtime"
        Invoke-Checked -Executable $venvPython -Arguments @("-m", "pip", "check") -Description "Checking dependency compatibility"
    }

    $checkArguments = @("-m", "scripts.check_debug_ui_environment")
    if (-not $SkipModelWarmup) {
        $checkArguments += "--warmup-models"
    }
    Invoke-Checked -Executable $venvPython -Arguments $checkArguments -Description "Verifying Poppler, imports, and OCR models"

    Write-Host "`nEnvironment is ready." -ForegroundColor Green
    Write-Host "Python: $venvPython"
    Write-Host "Run the app later with:"
    Write-Host ('& "{0}" -m streamlit run src\debug_ui\app.py' -f $venvPython) -ForegroundColor Yellow

    if ($Run) {
        $env:PYTHONUTF8 = "1"
        Invoke-Checked -Executable $venvPython -Arguments @(
            "-m", "streamlit", "run", "src\debug_ui\app.py"
        ) -Description "Starting the OCR debug UI"
    }
} finally {
    Set-Location -LiteralPath $previousLocation
}
