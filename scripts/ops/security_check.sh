#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# OpenEtruscan — Local Security Audit (fast)
# Combines Bandit SAST, pip-audit, and grep-based secret scanning.
# Usage:  bash scripts/security_check.sh
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAIL=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  OpenEtruscan Security Audit"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Bandit (SAST) ──────────────────────────────────────────────────
echo -e "\n${YELLOW}[1/4] Bandit — Static Analysis${NC}"
if command -v bandit &> /dev/null; then
    if bandit -r src/openetruscan/ -ll -ii -q 2>/dev/null; then
        echo -e "${GREEN}  ✅ No high/medium severity issues${NC}"
    else
        echo -e "${RED}  ❌ Bandit found issues (see above)${NC}"
        FAIL=1
    fi
else
    echo -e "${YELLOW}  ⚠️  bandit not installed (pip install bandit)${NC}"
fi

# ── 2. pip-audit (dependency vulns) ───────────────────────────────────
echo -e "\n${YELLOW}[2/4] pip-audit — Dependency Vulnerabilities${NC}"
if command -v pip-audit &> /dev/null; then
    if pip-audit --desc 2>/dev/null; then
        echo -e "${GREEN}  ✅ No known vulnerabilities${NC}"
    else
        echo -e "${RED}  ❌ Vulnerable packages found (see above)${NC}"
        FAIL=1
    fi
else
    echo -e "${YELLOW}  ⚠️  pip-audit not installed (pip install pip-audit)${NC}"
fi

# ── 3. Secret scanning (grep) ────────────────────────────────────────
echo -e "\n${YELLOW}[3/4] Secret Scan — Tracked Files${NC}"
SECRETS_FOUND=0

# Check if any .env files are tracked by git
if git ls-files --error-unmatch .env .env.local .env.production 2>/dev/null; then
    echo -e "${RED}  ❌ .env files are tracked by git!${NC}"
    SECRETS_FOUND=1
fi

# Grep for common secret patterns in tracked Python/YAML/JSON files
PATTERNS='(AIzaSy|sk-[a-zA-Z0-9]{20,}|hf_[a-zA-Z0-9]{10,}|ghp_|ghs_|AKIA[A-Z0-9]{16})'
if git grep -lPi "$PATTERNS" -- '*.py' '*.yml' '*.yaml' '*.json' '*.toml' ':!*lock*' ':!node_modules' 2>/dev/null; then
    echo -e "${RED}  ❌ Possible secrets found in tracked files (see above)${NC}"
    SECRETS_FOUND=1
fi

if [ $SECRETS_FOUND -eq 0 ]; then
    echo -e "${GREEN}  ✅ No secrets detected in tracked files${NC}"
else
    FAIL=1
fi

# ── 4. Dockerfile best practices ─────────────────────────────────────
echo -e "\n${YELLOW}[4/4] Dockerfile — Security Checks${NC}"
DOCKER_ISSUES=0

if grep -q "^USER " Dockerfile 2>/dev/null; then
    echo -e "${GREEN}  ✅ Non-root user configured${NC}"
else
    echo -e "${RED}  ❌ No USER directive — container runs as root${NC}"
    DOCKER_ISSUES=1
fi

if grep -q "AS builder\|AS build" Dockerfile 2>/dev/null; then
    echo -e "${GREEN}  ✅ Multi-stage build detected${NC}"
else
    echo -e "${YELLOW}  ⚠️  No multi-stage build — build deps may ship in image${NC}"
fi

if [ $DOCKER_ISSUES -gt 0 ]; then
    FAIL=1
fi

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}  All checks passed ✅${NC}"
else
    echo -e "${RED}  Some checks failed ❌ — review output above${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit $FAIL
