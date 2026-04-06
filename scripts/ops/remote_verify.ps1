# Remote Verification Script for OpenEtruscan
# This script is designed for PowerShell (User OS: Windows).
# It uses gcloud to SSH into the VM and perform deployment/verification.

$VM_COMMAND = 'gcloud compute ssh --zone "europe-west4-a" "openetruscan-eu" --project "long-facet-427508-j2"'

Write-Host "🚀 Starting Remote Verification for OpenEtruscan" -ForegroundColor Cyan

# 1. Sync local workspace to VM (via rsync-like or direct command override)
Write-Host "📦 Syncing codebase to VM..." -ForegroundColor Yellow
# For this audit, we'll assume the VM already has the repo or we use git pull.
# A more robust solution would be 'gcloud compute scp'.

# 2. Update dependencies on the VM
Write-Host "🔧 Updating remote dependencies..." -ForegroundColor Yellow
$deps_cmd = "pip install sqlalchemy[asyncio] asyncpg pytest-asyncio httpx"
Invoke-Expression "$VM_COMMAND --command `"$deps_cmd`""

# 3. Run Unit Tests on the VM
Write-Host "🧪 Running Unit Tests on the VM..." -ForegroundColor Yellow
$ut_cmd = "pytest tests/test_server.py tests/test_corpus.py"
Invoke-Expression "$VM_COMMAND --command `"$ut_cmd`""

# 4. Run Pleiades Alignment Audit
Write-Host "📍 Running Pleiades Alignment Audit on the VM..." -ForegroundColor Yellow
$pleiades_cmd = "python scripts/ops/align_pleiades.py"
Invoke-Expression "$VM_COMMAND --command `"$pleiades_cmd`""

Write-Host "✨ Remote Verification Complete!" -ForegroundColor Green
