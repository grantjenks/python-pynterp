#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/todo_loop.sh [options]

Repeatedly runs `codex exec` in fresh processes to burn down TODO.md.

Options:
  -n, --max-iterations N   Maximum loop count (default: 1000)
  --max-stagnant N         Stop after N no-progress iterations (default: 10)
  --sleep SECONDS          Delay between iterations (default: 1)
  -C, --cd DIR             Repository/work dir for codex and git (default: .)
  --log-dir DIR            Directory for per-iteration logs (default: .todo-loop)
  -m, --model MODEL        Optional codex model
  -p, --profile PROFILE    Optional codex profile
  --prompt-file FILE       Append extra instructions from file
  --done-token TOKEN       Completion token to detect in final message
                           (default: TODO_LOOP_DONE)
  --allow-dirty            Allow starting with a dirty working tree (default behavior)
  --no-allow-dirty         Require a clean working tree before starting
  --codex-bin PATH         Codex binary to use (default: codex)
  -h, --help               Show this help

Example:
  scripts/todo_loop.sh -n 10 --max-stagnant 3
EOF
}

MAX_ITERATIONS=1000
MAX_STAGNANT=10
SLEEP_SECONDS=1
WORKDIR="."
LOG_DIR=".todo-loop"
MODEL=""
PROFILE=""
PROMPT_FILE=""
DONE_TOKEN="TODO_LOOP_DONE"
ALLOW_DIRTY=1
CODEX_BIN="codex"

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
    --done-token)
      DONE_TOKEN="$2"
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

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "Codex binary not found: $CODEX_BIN" >&2
  exit 1
fi

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]] || [[ "$MAX_ITERATIONS" -lt 1 ]]; then
  echo "--max-iterations must be a positive integer" >&2
  exit 2
fi

if [[ ! "$MAX_STAGNANT" =~ ^[0-9]+$ ]] || [[ "$MAX_STAGNANT" -lt 1 ]]; then
  echo "--max-stagnant must be a positive integer" >&2
  exit 2
fi

if [[ ! "$SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "--sleep must be a non-negative integer" >&2
  exit 2
fi

WORKDIR="$(cd "$WORKDIR" && pwd)"
LOG_DIR_ABS="$WORKDIR/$LOG_DIR"
mkdir -p "$LOG_DIR_ABS"

if [[ -n "$PROMPT_FILE" ]] && [[ ! -f "$PROMPT_FILE" ]]; then
  echo "--prompt-file not found: $PROMPT_FILE" >&2
  exit 2
fi

if ! git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Directory is not a git repository: $WORKDIR" >&2
  exit 1
fi

if [[ "$ALLOW_DIRTY" -eq 0 ]] && [[ -n "$(git -C "$WORKDIR" status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit/stash first, or pass --allow-dirty." >&2
  exit 1
fi

read -r -d '' BASE_PROMPT <<EOF || true
You are running inside an iterative TODO loop to make progress on TODO.md.

Rules for this single iteration:
1) Read TODO.md and choose the highest-priority actionable item not marked done or SKIP.
2) Implement one meaningful slice that improves that item.
3) Run targeted checks/tests (prefer uv run pytest with narrow scope first).
4) Update TODO.md with concise progress notes and any metric deltas.
5) If checks pass and changes exist, commit with message: todo: <short summary>.

Stop condition:
- If TODO.md has no actionable items remaining, print exactly: $DONE_TOKEN
- If blocked, write the blocker to TODO.md and summarize the blocker briefly.
EOF

EXTRA_PROMPT=""
if [[ -n "$PROMPT_FILE" ]]; then
  EXTRA_PROMPT="$(cat "$PROMPT_FILE")"
fi

stagnant=0
echo "Starting TODO loop in $WORKDIR"
echo "Logs: $LOG_DIR_ABS"
echo "Max iterations: $MAX_ITERATIONS | Max stagnant: $MAX_STAGNANT"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  before_head="$(git -C "$WORKDIR" rev-parse HEAD)"
  before_status="$(git -C "$WORKDIR" status --porcelain)"

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

  cmd=("$CODEX_BIN" exec "--cd" "$WORKDIR" "--full-auto" "--color" "never" "--output-last-message" "$last_msg")
  if [[ -n "$MODEL" ]]; then
    cmd+=("--model" "$MODEL")
  fi
  if [[ -n "$PROFILE" ]]; then
    cmd+=("--profile" "$PROFILE")
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

  if [[ -f "$last_msg" ]] && grep -Fq "$DONE_TOKEN" "$last_msg"; then
    echo "Done token detected in iteration $i. Exiting loop."
    exit 0
  fi

  after_head="$(git -C "$WORKDIR" rev-parse HEAD)"
  after_status="$(git -C "$WORKDIR" status --porcelain)"

  progressed=0
  if [[ "$after_head" != "$before_head" ]]; then
    progressed=1
  elif [[ "$after_status" != "$before_status" ]]; then
    progressed=1
  fi

  if [[ "$progressed" -eq 1 ]]; then
    stagnant=0
    echo "Progress detected."
  else
    stagnant=$((stagnant + 1))
    echo "No repo change detected (stagnant=$stagnant/$MAX_STAGNANT)."
  fi

  if [[ "$stagnant" -ge "$MAX_STAGNANT" ]]; then
    echo "Stopping: reached max stagnant iterations."
    exit 0
  fi

  if [[ "$i" -lt "$MAX_ITERATIONS" ]] && [[ "$SLEEP_SECONDS" -gt 0 ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

echo "Reached max iterations: $MAX_ITERATIONS"
