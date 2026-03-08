---
name: bump-version
description: Bump the pynterp package version, publish a new release, and redeploy the live www service. Use when asked to cut a patch or minor release, update release metadata, wait for GitHub Actions and PyPI, push the matching vX.Y.Z tag, or roll Cloud Run to the same package and image version.
---

# Bump Version

Follow the repo's exact release path. `main` must be green before tagging, `.github/workflows/release.yml` publishes to PyPI from a pushed `v*` tag, and `www` must be redeployed only after PyPI serves the new version because the container installs `pynterp` from PyPI.

## Update files

Update these files together for every release:

- `pyproject.toml`: canonical package version
- `uv.lock`: editable package version; refresh with `uv lock`
- `www/Dockerfile`: default `ARG PYNTERP_VERSION`
- `www/SETUP.md`: example Artifact Registry image tag

Do not edit `.github/workflows/ci.yml` or `.github/workflows/release.yml` unless the user explicitly asks to change release automation.

## Validate locally

Run the same checks as CI from the repo root:

```bash
uv lock
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

Fix any failure before committing. Keep the worktree clean except for the intended release changes.

## Push main and wait for CI

Commit and push only after local checks pass:

```bash
git add pyproject.toml uv.lock www/Dockerfile www/SETUP.md
git commit -m "Bump version to X.Y.Z"
git push origin main
```

Wait for the `CI` workflow on that exact commit to finish green:

```bash
gh run list --limit 5 --json databaseId,headBranch,headSha,status,conclusion,workflowName,displayTitle,url
gh run view <run-id> --json status,conclusion,jobs,url
```

If `main` CI fails, fix the failure on `main`, rerun local checks, push again, and wait for green before tagging.

## Tag and publish

Create an annotated tag only after `main` is green:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Wait for the `Release` workflow to finish green. Confirm the publish job completed before proceeding.

If a tag run fails before PyPI publication, fix the issue on `main` and decide whether to reuse the version or cut the next one based on whether artifacts already appeared on PyPI. If PyPI already serves `X.Y.Z`, never try to overwrite it; bump again.

## Wait for PyPI

Verify the live index, not just GitHub Actions:

```bash
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/pynterp/json", timeout=20) as resp:
    data = json.load(resp)
print(data["info"]["version"])
print("X.Y.Z" in data["releases"])
PY
```

Proceed only when the reported version is `X.Y.Z` and the release exists.

## Redeploy www

The live challenge service is `pynterp-ctf` in project `pynterp-ctf-project`, region `us-west1`. The image tag should match the package version.

Prepare Docker auth:

```bash
gcloud auth configure-docker us-west1-docker.pkg.dev --quiet
```

Build the image from the repo root. Source `.env` inside the shell so `FLAG_VALUE` does not get printed separately:

```bash
bash -lc 'set -a; . ./.env; set +a; docker build \
  --platform linux/amd64 \
  --build-arg FLAG_VALUE="$FLAG_VALUE" \
  --build-arg PYNTERP_VERSION=X.Y.Z \
  -t us-west1-docker.pkg.dev/pynterp-ctf-project/pynterp/pynterp-www:X.Y.Z \
  ./www'
```

Push and deploy:

```bash
docker push us-west1-docker.pkg.dev/pynterp-ctf-project/pynterp/pynterp-www:X.Y.Z

gcloud run deploy pynterp-ctf \
  --image us-west1-docker.pkg.dev/pynterp-ctf-project/pynterp/pynterp-www:X.Y.Z \
  --region us-west1 \
  --allow-unauthenticated \
  --service-account pynterp-ctf-runtime@pynterp-ctf-project.iam.gserviceaccount.com \
  --execution-environment=gen1 \
  --memory=128Mi \
  --cpu=0.25 \
  --concurrency=1 \
  --timeout=15s \
  --min-instances=0 \
  --max-instances=1 \
  --network=pynterp-net \
  --subnet=pynterp-subnet \
  --network-tags=pynterp-egress-blocked \
  --vpc-egress=all-traffic \
  --quiet
```

## Smoke test and report

Confirm the service rolled to the new image and the public site still works:

```bash
gcloud run services describe pynterp-ctf --region=us-west1 --format='value(spec.template.spec.containers[0].image,status.latestReadyRevisionName,status.url)'
curl -sS https://pynterp.gmj.dev/ | head -n 5
curl -sS -X POST https://pynterp.gmj.dev/run \
  -H 'content-type: application/json' \
  -d '{"code":"print(1 + 2)"}'
```

Report the new version, main commit sha, tag, CI URL, Release URL, PyPI confirmation, deployed revision/image, and smoke-test result.
