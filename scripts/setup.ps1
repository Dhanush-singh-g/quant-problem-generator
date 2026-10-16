param([string]$AdminEmail = "admin@example.com", [switch]$ConfigureOnly)
$ErrorActionPreference = "Stop"
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    function New-Secret([int]$Bytes = 48) {
        $buffer = New-Object byte[] $Bytes
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
        return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+','-').Replace('/','_')
    }
    if (-not (Test-Path -LiteralPath ".env")) {
        if ($AdminEmail -notmatch '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$') { throw "Enter a valid administrator email." }
        $config = @(
            "ENVIRONMENT=development", "WEB_PORT=3000", "POSTGRES_PASSWORD=$(New-Secret 24)",
            "JWT_SECRET=$(New-Secret)", "ASSIGNMENT_SECRET=$(New-Secret)",
            "ADMIN_EMAIL=$AdminEmail", "ADMIN_PASSWORD=$(New-Secret 18)", "BOOTSTRAP_ADMIN=true",
            "AUTO_CREATE_SCHEMA=false", "COOKIE_SECURE=false", "COOKIE_SAMESITE=lax",
            "CORS_ORIGINS=http://localhost:3000", "RATE_LIMIT_FAIL_OPEN=false",
            "REVEAL_RESULTS_WHILE_ACTIVE=false", "ENABLE_PRACTICE_MODE=true",
            "GENERATION_USE_AI_CONTEXT=false", "GENERATION_MAX_PENDING_PER_BUCKET=5"
        )
        [IO.File]::WriteAllLines((Join-Path (Get-Location) '.env'), $config, (New-Object Text.UTF8Encoding $false))
        Write-Host "Created local configuration with independent random secrets. Admin credentials are in .env; keep that file private."
    } else {
        Write-Host "Preserving your existing .env. No credentials were replaced."
    }
    if ($ConfigureOnly) { return }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Install Docker Desktop with the WSL 2 backend, open it, then rerun this script." }
    $dockerOS = docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0) { throw "Start Docker Desktop in Linux-container mode, then rerun this script." }
    if ($dockerOS.Trim() -ne 'linux') { throw "Switch Docker Desktop to Linux containers, then rerun this script." }
    docker compose version
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 is required. Update Docker Desktop." }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Configuration is incomplete. Compare .env with .env.example without overwriting existing credentials." }
    docker compose up -d --build --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) { throw "Startup failed. Run docker compose logs --tail=100 to identify the service." }
    docker compose exec -T api python -m app.seed --per-bucket 10
    if ($LASTEXITCODE -ne 0) { throw "Starter inventory failed. Existing data is preserved; inspect the API logs." }
    Write-Host "QuantForge is running. Open http://localhost:3000 and sign in using ADMIN_EMAIL and ADMIN_PASSWORD from .env."
    Write-Host "Stop with docker compose down. Restart with docker compose up -d --wait. Avoid down -v: that deletes local data."
} finally { Pop-Location }
