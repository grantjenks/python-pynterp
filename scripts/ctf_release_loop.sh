#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/ctf_release_loop.sh [options]

Repeatedly runs `codex exec` in fresh headless sessions to:
1. find one live CTF exploit,
2. turn it into a regression test and fix,
3. land the fix on main and wait for green CI,
4. bump the patch version and redeploy,
5. verify the exploit is blocked in production,
6. then return to step 1.

The loop stops immediately if Codex reports that the fix is too complex or
needs design input. If Codex reports no live finding, the loop keeps trying
until it reaches the stagnant-iteration limit.

Options:
  -n, --max-iterations N   Maximum loop count (default: 1000)
  --max-stagnant N         Stop after N no-finding/no-progress iterations
                           (default: 5, 0 disables)
  --sleep SECONDS          Delay between iterations (default: 1)
  -C, --cd DIR             Repository/work dir for codex and git (default: .)
  --log-dir DIR            Directory for per-iteration logs
                           (default: .ctf-release-loop)
  --branch NAME            Required git branch (default: main)
  --prod-url URL           Live service base URL (default: https://pynterp.gmj.dev)
  -m, --model MODEL        Optional codex model
  -p, --profile PROFILE    Optional codex profile
  --prompt-file FILE       Append extra instructions from file
  --allow-dirty            Allow starting with a dirty worktree
  --no-allow-dirty         Require a clean worktree before starting (default)
  --codex-bin PATH         Codex binary to use (default: codex)
  -h, --help               Show this help

Notes:
  - The script invokes Codex with
    `--dangerously-bypass-approvals-and-sandbox` because the workflow needs
    unrestricted git, network, docker, gh, and gcloud access.
  - The loop relies on repo-local AGENTS/skill files for
    `capture-the-flag` and `bump-version`.
EOF
}

MAX_ITERATIONS=1000
MAX_STAGNANT=5
SLEEP_SECONDS=1
WORKDIR="."
LOG_DIR=".ctf-release-loop"
BRANCH="main"
PROD_URL="https://pynterp.gmj.dev"
MODEL=""
PROFILE=""
PROMPT_FILE=""
ALLOW_DIRTY=0
CODEX_BIN="codex"

CONTINUE_TOKEN="CTF_RELEASE_LOOP_CONTINUE"
BLOCKED_TOKEN="CTF_RELEASE_LOOP_BLOCKED"
NO_FINDING_TOKEN="CTF_RELEASE_LOOP_NO_FINDING"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--max-iterations)
      MAX_ITERATIONS="$2"
      shift 2
      ;;
    --max-stagnant)
      MAX_STAGNANT="$2"
      shift 2
      ;;
    --sleep)
      SLEEP_SECONDS="$2"
      shift 2
      ;;
    -C|--cd)
      WORKDIR="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --prod-url)
      PROD_URL="$2"
      shift 2
      ;;
    -m|--model)
      MODEL="$2"
      shift 2
      ;;
    -p|--profile)
      PROFILE="$2"
      shift 2
      ;;
    --prompt-file)
      PROMPT_FILE="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --no-allow-dirty)
      ALLOW_DIRTY=0
      shift
      ;;
    --codex-bin)
      CODEX_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]] || [[ "$MAX_ITERATIONS" -lt 1 ]]; then
  echo "--max-iterations must be a positive integer" >&2
  exit 2
fi

if [[ ! "$MAX_STAGNANT" =~ ^[0-9]+$ ]]; then
  echo "--max-stagnant must be a non-negative integer" >&2
  exit 2
fi

if [[ ! "$SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "--sleep must be a non-negative integer" >&2
  exit 2
fi

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "Codex binary not found: $CODEX_BIN" >&2
  exit 1
fi

for tool in git uv gh docker gcloud python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Required tool not found: $tool" >&2
    exit 1
  fi
done

WORKDIR="$(cd "$WORKDIR" && pwd)"

if [[ -n "$PROMPT_FILE" ]] && [[ ! -f "$PROMPT_FILE" ]]; then
  echo "--prompt-file not found: $PROMPT_FILE" >&2
  exit 2
fi

if ! git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Directory is not a git repository: $WORKDIR" >&2
  exit 1
fi

current_branch="$(git -C "$WORKDIR" branch --show-current)"
if [[ -n "$BRANCH" ]] && [[ "$current_branch" != "$BRANCH" ]]; then
  echo "Expected branch '$BRANCH', found '$current_branch'" >&2
  exit 1
fi

CTF_SKILL_PATH="$WORKDIR/.agents/skills/capture-the-flag/SKILL.md"
BUMP_SKILL_PATH="$WORKDIR/.agents/skills/bump-version/SKILL.md"

for skill_path in "$CTF_SKILL_PATH" "$BUMP_SKILL_PATH"; do
  if [[ ! -f "$skill_path" ]]; then
    echo "Required skill file not found: $skill_path" >&2
    exit 1
  fi
done

if [[ "$LOG_DIR" = /* ]]; then
  LOG_DIR_ABS="$LOG_DIR"
else
  LOG_DIR_ABS="$WORKDIR/$LOG_DIR"
fi

LOG_DIR_REL="${LOG_DIR_ABS#$WORKDIR/}"
if [[ "$LOG_DIR_REL" == "$LOG_DIR_ABS" ]]; then
  LOG_DIR_REL=""
fi

repo_changes_output() {
  (
    cd "$WORKDIR"
    status_args=(--porcelain --untracked-files=all -- .)
    if [[ -n "$LOG_DIR_REL" ]]; then
      status_args+=(":(exclude)$LOG_DIR_REL")
    fi
    git status "${status_args[@]}"
  )
}

repo_state_fingerprint() {
  (
    cd "$WORKDIR"
    {
      git rev-parse HEAD

      tracked_args=(--no-ext-diff --binary -- .)
      if [[ -n "$LOG_DIR_REL" ]]; then
        tracked_args+=(":(exclude)$LOG_DIR_REL")
      fi
      git diff "${tracked_args[@]}"
      git diff --cached "${tracked_args[@]}"

      while IFS= read -r path; do
        if [[ -n "$LOG_DIR_REL" ]]; then
          case "$path" in
            "$LOG_DIR_REL"|"$LOG_DIR_REL"/*) continue ;;
          esac
        fi
        printf 'UNTRACKED %s\n' "$path"
        if [[ -f "$path" ]]; then
          shasum "$path"
        else
          printf 'NONFILE\n'
        fi
      done < <(git ls-files --others --exclude-standard -- .)
    } | shasum | awk '{print $1}'
  )
}

if [[ "$ALLOW_DIRTY" -eq 0 ]] && [[ -n "$(repo_changes_output)" ]]; then
  echo "Working tree is dirty. Commit/stash first, or pass --allow-dirty." >&2
  exit 1
fi

mkdir -p "$LOG_DIR_ABS"

read -r -d '' BASE_PROMPT <<EOF || true
You are running inside an automated exploit-fix-release loop for this repository.

Use these repo-local skills and follow their workflows exactly in this iteration:
- [\$capture-the-flag]($CTF_SKILL_PATH)
- [\$bump-version]($BUMP_SKILL_PATH)

Complete exactly one exploit cycle end-to-end for this iteration:
1. Establish the real target and success channel first from README.md, www/app.py, www/Dockerfile, src/pynterp/, and the security tests.
2. Reproduce locally as early as possible, matching the real runtime when behavior could be version-sensitive.
3. Find one currently working exploit against $PROD_URL that actually reveals /challenge/flag.txt in production.
   - Keep probes short and only promote locally working primitives to production.
   - If you cannot confirm a live exploit after focused search, make no release changes, explain briefly, and print exactly: $NO_FINDING_TOKEN
4. Turn the confirmed exploit into a regression test and a fix.
   - If the right fix is too complex, risky, or needs design input, stop immediately, explain briefly, and print exactly: $BLOCKED_TOKEN
5. Run the necessary local checks. Commit and push the fix on $BRANCH. If CI fails, fix $BRANCH, rerun checks, push again, and continue until the exact CI run for the current HEAD is green.
6. Use [\$bump-version]($BUMP_SKILL_PATH) to increment the patch version, publish the release, wait for PyPI propagation and installability, redeploy the live www service, and smoke test it.
7. Re-run the exact exploit payload against production and confirm it is blocked now.
8. Leave the worktree clean, summarize the exploit/fix/release/deploy results, and print exactly: $CONTINUE_TOKEN

Constraints:
- Work from $WORKDIR on branch $BRANCH.
- Do not edit .github/workflows/*.yml unless explicitly required.
- Do not batch multiple exploits into one iteration.
- If production is already fixed before you can confirm a live exploit, treat that as no live finding.
- If you print $NO_FINDING_TOKEN or $BLOCKED_TOKEN, do not create a release tag.
EOF

EXTRA_PROMPT=""
if [[ -n "$PROMPT_FILE" ]]; then
  EXTRA_PROMPT="$(cat "$PROMPT_FILE")"
fi

stagnant=0
echo "Starting CTF release loop in $WORKDIR"
echo "Logs: $LOG_DIR_ABS"
echo "Branch: $BRANCH | Prod URL: $PROD_URL"
echo "Max iterations: $MAX_ITERATIONS | Max stagnant: $MAX_STAGNANT"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  before_head="$(git -C "$WORKDIR" rev-parse HEAD)"
  before_state="$(repo_state_fingerprint)"

  iter_prompt="$BASE_PROMPT

Iteration: $i / $MAX_ITERATIONS
Current HEAD: $before_head"
  if [[ -n "$EXTRA_PROMPT" ]]; then
    iter_prompt="$iter_prompt

Additional instructions:
$EXTRA_PROMPT"
  fi

  log_file="$LOG_DIR_ABS/iter-$(printf '%03d' "$i").log"
  last_msg="$LOG_DIR_ABS/iter-$(printf '%03d' "$i").last-message.txt"

  cmd=(
    "$CODEX_BIN" exec
    --cd "$WORKDIR"
    --dangerously-bypass-approvals-and-sandbox
    --ephemeral
    --color never
    --output-last-message "$last_msg"
  )
  if [[ -n "$MODEL" ]]; then
    cmd+=(--model "$MODEL")
  fi
  if [[ -n "$PROFILE" ]]; then
    cmd+=(--profile "$PROFILE")
  fi

  echo
  echo "=== Iteration $i/$MAX_ITERATIONS ==="
  echo "Command: ${cmd[*]}"

  set +e
  printf '%s\n' "$iter_prompt" | "${cmd[@]}" - | tee "$log_file"
  rc=${PIPESTATUS[1]}
  set -e

  if [[ "$rc" -ne 0 ]]; then
    echo "Iteration $i failed (exit $rc). See $log_file" >&2
    exit "$rc"
  fi

  last_msg_text=""
  if [[ -f "$last_msg" ]]; then
    last_msg_text="$(cat "$last_msg")"
  fi

  if grep -Fq "$BLOCKED_TOKEN" <<<"$last_msg_text"; then
    echo "Blocked token detected in iteration $i. Stopping for manual input."
    exit 3
  fi

  after_head="$(git -C "$WORKDIR" rev-parse HEAD)"
  after_state="$(repo_state_fingerprint)"
  after_branch="$(git -C "$WORKDIR" branch --show-current)"

  if [[ -n "$BRANCH" ]] && [[ "$after_branch" != "$BRANCH" ]]; then
    echo "Iteration $i ended on branch '$after_branch', expected '$BRANCH'." >&2
    exit 4
  fi

  progressed=0
  if [[ "$after_head" != "$before_head" ]]; then
    progressed=1
  elif [[ "$after_state" != "$before_state" ]]; then
    progressed=1
  fi

  if grep -Fq "$NO_FINDING_TOKEN" <<<"$last_msg_text"; then
    if [[ "$progressed" -eq 1 ]]; then
      echo "Iteration $i reported no finding but changed the repo. See $log_file" >&2
      exit 4
    fi
    stagnant=$((stagnant + 1))
    echo "No live finding reported (stagnant=$stagnant/$MAX_STAGNANT)."
  elif grep -Fq "$CONTINUE_TOKEN" <<<"$last_msg_text"; then
    if [[ -n "$(repo_changes_output)" ]]; then
      echo "Iteration $i reported success but left a dirty worktree. See $log_file" >&2
      exit 4
    fi
    stagnant=0
    echo "Successful exploit cycle completed."
  else
    if [[ "$progressed" -eq 1 ]]; then
      echo "Iteration $i changed the repo but did not emit a control token. See $log_file" >&2
      exit 4
    fi
    stagnant=$((stagnant + 1))
    echo "No repo change and no control token detected (stagnant=$stagnant/$MAX_STAGNANT)."
  fi

  if [[ "$MAX_STAGNANT" -gt 0 ]] && [[ "$stagnant" -ge "$MAX_STAGNANT" ]]; then
    echo "Stopping: reached max stagnant iterations."
    exit 0
  fi

  if [[ "$i" -lt "$MAX_ITERATIONS" ]] && [[ "$SLEEP_SECONDS" -gt 0 ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

echo "Reached max iterations: $MAX_ITERATIONS"
