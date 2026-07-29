# Codecov Setup Guide for KosDB

## Overview
This guide explains how to set up Codecov integration for the KosDB project using GitHub Actions.

## What Was Created
- `.github/workflows/ci.yml` - GitHub Actions workflow for automated testing and coverage reporting

## Features
- ✅ Runs on Python 3.9, 3.10, and 3.11
- ✅ Generates coverage reports with branch coverage
- ✅ Uploads reports to Codecov.io
- ✅ Caches pip dependencies for faster builds
- ✅ Posts coverage summary on PRs
- ✅ Archives coverage reports as artifacts

## Required Setup Steps

### 1. Get Codecov Token

1. Go to [codecov.io](https://codecov.io)
2. Sign in with your GitHub account
3. Find or add the KosDB repository
4. Go to Settings → General
5. Copy the **Repository Upload Token**

### 2. Add GitHub Secret

1. Go to your GitHub repository: `https://github.com/m5it/KosDB`
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `CODECOV_TOKEN`
5. Value: Paste your Codecov upload token
6. Click **Add secret**

### 3. Update requirements.txt (Optional)

Uncomment these lines in `requirements.txt`:
```txt
pytest>=6.0.0
pytest-cov>=2.10.0
```

### 4. Test the Workflow

Push any change to `main`, `master`, or `develop` branch:
```bash
git add .github/workflows/ci.yml
git commit -m "Add Codecov CI workflow"
git push origin main
```

## Workflow Triggers

The CI runs on:
- Push to: `main`, `master`, `develop`
- Pull requests to: `main`, `master`

## Viewing Results

1. **GitHub Actions**: Check the Actions tab in your repository
2. **Codecov Dashboard**: Visit `https://codecov.io/gh/m5it/KosDB`
3. **PR Comments**: Coverage summary appears on pull requests

## Troubleshooting

### Issue: "Token not found"
**Solution**: Ensure `CODECOV_TOKEN` secret is set in GitHub repository settings

### Issue: "leveldb not found"
**Solution**: The workflow installs `libleveldb-dev` automatically. If issues persist, check system compatibility.

### Issue: Tests fail but coverage uploads
**Solution**: This is expected behavior (`continue-on-error: true`). Fix tests separately.

## Local Testing

Run coverage locally before pushing:
```bash
# Install dependencies
pip install pytest pytest-cov
pip install -e .

# Run with coverage
pytest --cov=. --cov-branch --cov-report=xml --cov-report=term
```

## Badge (Add to README.md)

After first successful upload, add this badge:
```markdown
[![codecov](https://codecov.io/gh/m5it/KosDB/branch/main/graph/badge.svg)](https://codecov.io/gh/m5it/KosDB)
```

## Support

- Codecov Docs: https://docs.codecov.com/
- GitHub Actions Docs: https://docs.github.com/en/actions
