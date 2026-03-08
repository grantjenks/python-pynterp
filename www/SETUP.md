# `pynterp` Cloud Run setup

This directory contains a minimal Flask app that installs `pynterp` from PyPI in the container image and deploys to Cloud Run as a prebuilt image.

## Files

- `app.py`: tiny HTTP app with `/` and `/run`
- `Dockerfile`: container build used before deploying the image to Cloud Run

## Local development

From the repo root:

```bash
set -a
. ./.env
set +a

docker build --build-arg FLAG_VALUE="$FLAG_VALUE" -t pynterp-www ./www
docker run --rm -p 8080:8080 pynterp-www
```

The local build can use your native Docker architecture. For the image you push to Cloud Run, build `linux/amd64` explicitly.

Example requests:

```bash
curl http://127.0.0.1:8080/
curl -X POST http://127.0.0.1:8080/run \
  -H 'content-type: application/json' \
  -d '{"code":"print(1 + 2)"}'
```

## Google Cloud setup

The commands below assume:

- region: `us-west1`
- build context: `www/`
- execution environment: `gen1`
- memory: `128Mi`
- CPU: `0.25`
- concurrency: `1`
- max instances: `1`
- Direct VPC egress with `all-traffic`
- no roles on the runtime service account

### 1. Authenticate and choose values

```bash
gcloud auth login
gcloud --version

gcloud billing accounts list
read -rp 'Billing account ID: ' BILLING_ACCOUNT_ID

export PROJECT_ID="pynterp-ctf-project"
export PROJECT_NAME="pynterp CTF Project"

export REGION="us-west1"
export SERVICE="pynterp-ctf"
export REPOSITORY="pynterp"
export IMAGE="pynterp-www"

export NETWORK="pynterp-net"
export SUBNET="pynterp-subnet"
export SUBNET_RANGE="10.8.0.0/26"

export RUNTIME_SA_NAME="pynterp-ctf-runtime"
export TAG="pynterp-egress-blocked"

export DOMAIN="pynterp.gmj.dev"
export BASE_DOMAIN="gmj.dev"
```

### 2. Create the project and link billing

```bash
gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
gcloud config set project "$PROJECT_ID"

export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export DEPLOYER_EMAIL="$(gcloud config get-value account)"
export RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE}:0.2.1"
```

### 3. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  artifactregistry.googleapis.com
```

### 4. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Images for pynterp Cloud Run"
```

Configure Docker auth for Artifact Registry:

```bash
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
```

### 5. Create the VPC and subnet

```bash
gcloud compute networks create "$NETWORK" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --network="$NETWORK" \
  --region="$REGION" \
  --range="$SUBNET_RANGE"
```

### 6. Create the runtime service account

```bash
gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --display-name="pynterp CTF runtime"
```

Do not grant project roles to the runtime service account. Keep it empty for security.

### 7. Grant the deploy permissions

Allow your user to deploy a Cloud Run service that runs as the dedicated runtime service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="user:${DEPLOYER_EMAIL}" \
  --role="roles/iam.serviceAccountUser"
```

If your user is already a project `Owner` or `Editor`, that binding is the only extra IAM change required for this setup.

If your user is more restricted, grant the deployer the Cloud Run and Artifact Registry roles described in the Cloud Run IAM docs before continuing.

### 8. Add the egress deny firewall rule

```bash
gcloud compute firewall-rules create "${SERVICE}-deny-egress-ipv4" \
  --network="$NETWORK" \
  --direction=EGRESS \
  --priority=1000 \
  --action=DENY \
  --rules=all \
  --destination-ranges=0.0.0.0/0 \
  --target-tags="$TAG"
```

Notes:

- This rule blocks all IPv4 egress for revisions with the matching network tag, not just public internet access.
- Do not create Cloud NAT if the goal is to keep the service from reaching the public internet.

### 9. Build the image with the flag

Load the repo-root `.env`, build the image, and push it:

```bash
set -a
. ./.env
set +a

docker build \
  --platform linux/amd64 \
  --build-arg FLAG_VALUE="$FLAG_VALUE" \
  -t "$IMAGE_URL" \
  ./www

docker push "$IMAGE_URL"
```

This stores the flag in the built image. That is acceptable for this hobby setup, but it is not a secret-safe mechanism.

The explicit `--platform linux/amd64` matters on Apple Silicon. Without it, Docker builds an `arm64` image locally and Cloud Run fails to start the container with an `exec format error`.

### 10. Deploy to Cloud Run

Run this from the repo root:

```bash
gcloud run deploy "$SERVICE" \
  --image "$IMAGE_URL" \
  --region="$REGION" \
  --allow-unauthenticated \
  --service-account="$RUNTIME_SA" \
  --execution-environment=gen1 \
  --memory=128Mi \
  --cpu=0.25 \
  --concurrency=1 \
  --timeout=15s \
  --min-instances=0 \
  --max-instances=1 \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --network-tags="$TAG" \
  --vpc-egress=all-traffic
```

Notes:

- `--vpc-egress=all-traffic` forces all outbound traffic through the VPC path.
- `--network-tags="$TAG"` attaches the firewall tag to the deployed revision.

### 11. Smoke test the service

```bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$SERVICE_URL"

curl "$SERVICE_URL/"
curl -X POST "$SERVICE_URL/run" \
  -H 'content-type: application/json' \
  -d '{"code":"print(1 + 2)"}'
```

The app itself blocks imports by constructing `Interpreter(allowed_imports=set())`. The VPC and firewall setup is the outer network-control layer in case code escapes the interpreter sandbox.

### 12. Optional: verify outbound internet is blocked

Create a temporary Cloud Run job that uses the same image, service account, VPC settings, and network tag, but runs a simple outbound HTTPS probe:

```bash
gcloud run jobs create "${SERVICE}-egress-probe" \
  --image "$IMAGE_URL" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --tasks=1 \
  --parallelism=1 \
  --max-retries=0 \
  --task-timeout=30s \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --network-tags="$TAG" \
  --vpc-egress=all-traffic \
  --command=python \
  --args=-c,"import urllib.request; urllib.request.urlopen('https://example.com/', timeout=5)"
```

Run it and expect the execution to fail:

```bash
gcloud run jobs execute "${SERVICE}-egress-probe" \
  --region="$REGION" \
  --wait || true
```

Then inspect the logs. A timeout or `Network is unreachable` result is the expected outcome.

```bash
gcloud logging read \
  "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${SERVICE}-egress-probe\"" \
  --limit=20
```

Clean up the temporary job afterward:

```bash
gcloud run jobs delete "${SERVICE}-egress-probe" \
  --region="$REGION" \
  --quiet
```

### 13. Map the custom domain

Cloud Run domain mapping is still Preview and not recommended for production services, but it is the cheap option for this hobby setup.

Verify domain ownership:

```bash
gcloud domains list-user-verified
gcloud domains verify "$BASE_DOMAIN"
```

If the parent domain already appears in `gcloud domains list-user-verified`, you can skip `gcloud domains verify`.

Make sure the beta command group is installed before creating the mapping:

```bash
gcloud components install beta --quiet
```

Create the mapping:

```bash
gcloud beta run domain-mappings create \
  --service "$SERVICE" \
  --domain "$DOMAIN" \
  --region "$REGION"
```

Fetch the DNS records to add at your registrar:

```bash
gcloud beta run domain-mappings describe \
  --domain "$DOMAIN" \
  --region "$REGION"
```

Use the returned `resourceRecords` exactly as shown.

After you add the returned DNS records at your registrar, wait for `gcloud beta run domain-mappings describe` to show both `Ready: True` and `CertificateProvisioned: True`. In practice, the HTTPS endpoint can still lag behind those control-plane states for a few more minutes before it starts serving normally.

## References

- Artifact Registry Docker auth: <https://cloud.google.com/artifact-registry/docs/docker/authentication>
- Direct VPC egress: <https://cloud.google.com/run/docs/configuring/vpc-direct-vpc>
- Cloud Run IAM roles: <https://cloud.google.com/run/docs/reference/iam/roles>
- Cloud Run domain mapping: <https://cloud.google.com/run/docs/mapping-custom-domains>
