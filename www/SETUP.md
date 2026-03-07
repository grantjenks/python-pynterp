# `pynterp` Cloud Run setup

This directory contains a minimal Flask app that installs `pynterp` from PyPI in the container image and deploys to Cloud Run as a prebuilt image.

## Files

- `app.py`: tiny HTTP app with `/` and `/run`
- `Dockerfile`: container build used before deploying the image to Cloud Run

## Local development

From the repo root:

```bash
docker build --build-arg FLAG_VALUE='pynterp{local-test-flag}' -t pynterp-www ./www
docker run --rm -p 8080:8080 pynterp-www
```

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

export PROJECT_ID="pynterp-ctf-demo"
export PROJECT_NAME="pynterp CTF Demo"
export BILLING_ACCOUNT_ID="$(gcloud billing accounts list \
  --filter='open=true' \
  --format='value(name.basename())' \
  | head -n 1)"

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
export IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE}:0.1.0"
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

Grant the project roles needed to deploy the service:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${DEPLOYER_EMAIL}" \
  --role="roles/run.sourceDeveloper"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${DEPLOYER_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

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

Prompt locally for the flag value, build the image, and push it:

```bash
read -rsp 'Flag value: ' FLAG_VALUE
echo

docker build \
  --build-arg FLAG_VALUE="$FLAG_VALUE" \
  -t "$IMAGE_URL" \
  ./www

unset FLAG_VALUE

docker push "$IMAGE_URL"
```

This stores the flag in the built image. That is acceptable for this hobby setup, but it is not a secret-safe mechanism.

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

### 12. Map the custom domain

Cloud Run domain mapping is still Preview and not recommended for production services, but it is the cheap option for this hobby setup.

Verify domain ownership:

```bash
gcloud domains list-user-verified
gcloud domains verify "$BASE_DOMAIN"
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

## References

- Artifact Registry Docker auth: <https://cloud.google.com/artifact-registry/docs/docker/authentication>
- Direct VPC egress: <https://cloud.google.com/run/docs/configuring/vpc-direct-vpc>
- Cloud Run IAM roles: <https://cloud.google.com/run/docs/reference/iam/roles>
- Cloud Run domain mapping: <https://cloud.google.com/run/docs/mapping-custom-domains>
