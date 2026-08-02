$ErrorActionPreference = "Stop"

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
    $pythonExecutable = $pythonCommand.Source
} elseif (Test-Path "lab\structure_analysis_2\.venv\Scripts\python.exe") {
    $pythonExecutable = (Resolve-Path "lab\structure_analysis_2\.venv\Scripts\python.exe").Path
} else {
    throw "Không tìm thấy Python. Cài Python vào PATH hoặc tạo lab\\structure_analysis_2\\.venv."
}

Write-Host "=== Harness Initialization ==="

Write-Host "`nChecking project..."

if (Test-Path "frontend\package.json") {
    Write-Host "Installing frontend dependencies..."
    Push-Location frontend
    npm install
    npm run lint
    npm run typecheck
    Pop-Location
}

if (Test-Path "backend\requirements.txt") {
    Write-Host "Installing backend dependencies..."
    Push-Location backend
    pip install -r requirements.txt
    pytest
    Pop-Location
}

if (Test-Path "tests") {
    Write-Host "Running Python unit tests..."
    & $pythonExecutable -m unittest discover -s tests -p "test_*.py"
}

Write-Host "`n=== Verification Complete ==="

Write-Host "`nNext steps:"
Write-Host "1. Open progress.md"
Write-Host "2. Pick ONE unfinished feature from feature_list.json"
Write-Host "3. Implement the feature"
Write-Host "4. Run verification before marking it complete"
