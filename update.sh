#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  Fetchy — Update Utility
#  Usage: ./update.sh [--force-rebuild] [--no-pull] [--prune] [-h]
# ══════════════════════════════════════════════════════════════════
set -Eeuo pipefail

# ─────────────────────────────────────────────────────────────────
#  FLAGS
# ─────────────────────────────────────────────────────────────────
OPT_FORCE_REBUILD=false
OPT_NO_PULL=false
OPT_PRUNE=false

for arg in "$@"; do
  case "$arg" in
    --force-rebuild|-f) OPT_FORCE_REBUILD=true ;;
    --no-pull)          OPT_NO_PULL=true        ;;
    --prune|-p)         OPT_PRUNE=true          ;;
    --help|-h)
      echo ""
      echo "  Usage: ./update.sh [options]"
      echo ""
      echo "  Options:"
      echo "    --force-rebuild, -f   Rebuild Docker image without cache"
      echo "    --no-pull             Skip git pull (deploy current code)"
      echo "    --prune,         -p   Remove dangling images after build"
      echo "    --help,          -h   Show this help message"
      echo ""
      exit 0
      ;;
    *)
      echo "  Unknown option: $arg  (try --help)" >&2
      exit 1
      ;;
  esac
done

# ─────────────────────────────────────────────────────────────────
#  COLORS & STYLES
# ─────────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
WHITE="\033[1;37m"

c() { printf "\033[38;5;%dm" "$1"; }

TERM_WIDTH=$(tput cols 2>/dev/null || echo 80)

# ─────────────────────────────────────────────────────────────────
#  PRINT HELPERS
# ─────────────────────────────────────────────────────────────────
divider() {
  local width=$(( TERM_WIDTH < 64 ? TERM_WIDTH - 4 : 60 ))
  echo -e "  ${DIM}$(printf '%*s' "$width" '' | tr ' ' '-')${RESET}"
}

step_ok()   { echo -e "  ${GREEN}✔${RESET}  ${BOLD}$1${RESET}"; }
step_fail() { echo -e "  ${RED}✘${RESET}  ${BOLD}$1${RESET}"; }
step_warn() { echo -e "  ${YELLOW}⚠${RESET}  ${DIM}$1${RESET}"; }
step_info() { echo -e "  $(c 39)ℹ${RESET}  ${DIM}$1${RESET}"; }

section() {
  local num="$1" label="$2"
  echo -e "  ${BOLD}$(c 39)[${num}]${RESET}  ${WHITE}${label}${RESET}"
  echo ""
}

typewriter() {
  local text="$1" delay="${2:-0.028}" i
  for (( i=0; i<${#text}; i++ )); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
  echo
}

# ─────────────────────────────────────────────────────────────────
#  SPINNER
# ─────────────────────────────────────────────────────────────────
_SPINNER_PID=""
_SPINNER_FRAMES=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")

spinner_start() {
  local label="$1"
  (
    local i=0
    local cols=("\033[1;36m" "\033[1;34m" "\033[1;35m" "\033[1;36m")
    while true; do
      printf "\r  ${cols[$(( i % 4 ))]}${_SPINNER_FRAMES[$(( i % 10 ))]}${RESET}  %s" "$label" 2>/dev/null
      (( i++ )) || true
      sleep 0.08
    done
  ) &
  _SPINNER_PID=$!
}

spinner_stop() {
  [[ -n "$_SPINNER_PID" ]] || return 0
  kill "$_SPINNER_PID" 2>/dev/null || true
  wait "$_SPINNER_PID" 2>/dev/null || true
  _SPINNER_PID=""
  printf '\r\033[2K'
}

# ─────────────────────────────────────────────────────────────────
#  TASK RUNNER  — runs a command, shows spinner, reports result
#  run_task <label> <logfile> <cmd...>
# ─────────────────────────────────────────────────────────────────
run_task() {
  local label="$1" logfile="$2"; shift 2

  spinner_start "$label"

  local exit_code=0
  "$@" >"$logfile" 2>&1 || exit_code=$?

  spinner_stop

  if [[ $exit_code -ne 0 ]]; then
    step_fail "$label"
    echo ""
    echo -e "  ${RED}${BOLD}── Error output ─────────────────────────────────${RESET}"
    sed 's/^/    /' "$logfile" >&2
    echo -e "  ${RED}${BOLD}─────────────────────────────────────────────────${RESET}"
    echo ""
    return $exit_code
  fi

  step_ok "$label"
}

# ─────────────────────────────────────────────────────────────────
#  CLEANUP
# ─────────────────────────────────────────────────────────────────
_TMPDIR=""

cleanup() {
  spinner_stop
  [[ -n "$_TMPDIR" ]] && rm -rf "$_TMPDIR"
}

trap 'cleanup; echo -e "\n${RED}${BOLD}  ✘  Update aborted — check errors above.${RESET}\n" >&2' ERR
trap 'cleanup' EXIT

_TMPDIR=$(mktemp -d)

# ─────────────────────────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────────────────────────
clear

BANNER_COLORS=(51 45 39 33 27 21)
BANNER_LINES=(
  "  ███████╗███████╗████████╗ ██████╗██╗  ██╗██╗   ██╗"
  "  ██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║╚██╗ ██╔╝"
  "  █████╗  █████╗     ██║   ██║     ███████║ ╚████╔╝ "
  "  ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║  ╚██╔╝  "
  "  ██║     ███████╗   ██║   ╚██████╗██║  ██║   ██║   "
  "  ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝   ╚═╝  "
)

echo ""
for i in "${!BANNER_LINES[@]}"; do
  printf "$(c ${BANNER_COLORS[$i]})${BOLD}%s${RESET}\n" "${BANNER_LINES[$i]}"
  sleep 0.055
done

echo ""
printf "  ${DIM}"
typewriter "Your Elite Personal Media Assistant" 0.022
printf "  ${DIM}"
typewriter "── System Update Utility ──" 0.028
printf "${RESET}"
echo ""
divider
echo ""

# ─────────────────────────────────────────────────────────────────
#  [1/4]  PRE-FLIGHT CHECKS
# ─────────────────────────────────────────────────────────────────
TOTAL_STEPS=4
$OPT_NO_PULL && TOTAL_STEPS=3

section "1/${TOTAL_STEPS}" "Pre-flight Checks"

# git
if ! command -v git &>/dev/null; then
  step_fail "git not found — please install git"
  exit 1
fi
step_ok "git $(git --version | awk '{print $3}')"

# docker
if ! command -v docker &>/dev/null; then
  step_fail "docker not found — please install Docker"
  exit 1
fi
step_ok "docker $(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)"

# Detect: prefer 'docker compose' (v2 plugin), fall back to 'docker-compose'
if docker compose version &>/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  DOCKER_COMPOSE="docker-compose"
else
  step_fail "Neither 'docker compose' nor 'docker-compose' found"
  exit 1
fi
step_ok "compose engine: ${BOLD}${DOCKER_COMPOSE}${RESET}"

# Detect sudo need
if [[ $EUID -ne 0 ]] && ! docker info &>/dev/null 2>&1; then
  SUDO="sudo"
  step_info "Non-root user — will use sudo for Docker commands"
else
  SUDO=""
fi

# Project root guard
if [[ ! -f "docker-compose.yml" ]]; then
  step_fail "docker-compose.yml not found — run from the Fetchy project root"
  exit 1
fi
step_ok "docker-compose.yml present"

# .env guard
if [[ ! -f ".env" ]]; then
  step_warn ".env file missing"
  if [[ -f ".env.example" ]]; then
    echo ""
    echo -e "  ${YELLOW}${BOLD}  First-time setup detected!${RESET}"
    echo -e "  ${DIM}  Copying .env.example → .env${RESET}"
    cp .env.example .env
    echo ""
    echo -e "  ${YELLOW}${BOLD}  ⚠  Action required:${RESET}"
    echo -e "  ${DIM}  Edit ${BOLD}.env${RESET}${DIM} and fill in your DISCORD_BOT_TOKEN and other values${RESET}"
    echo -e "  ${DIM}  Then re-run this script.${RESET}"
    echo ""
    exit 0
  else
    step_fail ".env missing and no .env.example found — cannot continue"
    exit 1
  fi
fi
step_ok ".env file present"

# Version info
CURRENT_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)
BEFORE_SHA=$(git rev-parse HEAD)
step_info "Current version: ${BOLD}${CURRENT_VERSION}${RESET}"

# Active flags summary
FLAGS_ACTIVE=()
$OPT_FORCE_REBUILD && FLAGS_ACTIVE+=("--force-rebuild")
$OPT_NO_PULL       && FLAGS_ACTIVE+=("--no-pull")
$OPT_PRUNE         && FLAGS_ACTIVE+=("--prune")
if [[ ${#FLAGS_ACTIVE[@]} -gt 0 ]]; then
  step_info "Flags active: ${BOLD}${FLAGS_ACTIVE[*]}${RESET}"
fi

echo ""
divider
echo ""

# ─────────────────────────────────────────────────────────────────
#  [2/N]  GIT PULL  (skip if --no-pull)
# ─────────────────────────────────────────────────────────────────
STEP=2
if ! $OPT_NO_PULL; then
  section "${STEP}/${TOTAL_STEPS}" "Pulling Latest Changes"

  GIT_LOG="${_TMPDIR}/git_pull.log"
  run_task "Syncing with remote repository" "$GIT_LOG" \
    git pull --ff-only

  # ── Changelog ──────────────────────────────────────────────────
  AFTER_SHA=$(git rev-parse HEAD)
  if [[ "$BEFORE_SHA" == "$AFTER_SHA" ]]; then
    step_info "Already up to date — no new commits"
  else
    COMMITS=$(git log --pretty=format:"%h|%s" "${BEFORE_SHA}..${AFTER_SHA}" 2>/dev/null || true)
    COUNT=$(echo "$COMMITS" | grep -c . || true)

    echo ""
    echo -e "  $(c 39)${BOLD}ℹ${RESET}  ${BOLD}${COUNT} new commit$([ "$COUNT" -ne 1 ] && echo 's' || true) pulled:${RESET}"
    echo ""

    MAX_LEN=$(( TERM_WIDTH - 18 ))
    while IFS='|' read -r hash subject; do
      local icon color
      case "$subject" in
        feat*|feature*)    icon="✨"; color="$(c 84)"  ;;
        fix*|bugfix*)      icon="🐛"; color="$(c 203)" ;;
        docs*)             icon="📖"; color="$(c 75)"  ;;
        refactor*)         icon="♻️ "; color="$(c 141)" ;;
        perf*)             icon="⚡"; color="$(c 214)" ;;
        chore*|ci*|build*) icon="🔧"; color="$(c 245)" ;;
        test*)             icon="🧪"; color="$(c 111)" ;;
        style*)            icon="🎨"; color="$(c 219)" ;;
        revert*)           icon="⏪"; color="$(c 196)" ;;
        *)                 icon="▸";  color="$(c 252)" ;;
      esac
      (( ${#subject} > MAX_LEN )) && subject="${subject:0:$MAX_LEN}…"
      printf "  ${DIM}%s${RESET}  %s ${color}%s${RESET}\n" "$hash" "$icon" "$subject"
      sleep 0.04
    done <<< "$COMMITS"
  fi
  echo ""
  divider
  echo ""
  (( STEP++ ))
fi

# ─────────────────────────────────────────────────────────────────
#  [3/4]  DOCKER BUILD
# ─────────────────────────────────────────────────────────────────
section "${STEP}/${TOTAL_STEPS}" "Rebuilding Docker Image"

BUILD_LOG="${_TMPDIR}/docker_build.log"
BUILD_EXTRA_FLAGS=()
$OPT_FORCE_REBUILD && BUILD_EXTRA_FLAGS+=("--no-cache")

run_task "Building Docker image${OPT_FORCE_REBUILD:+ (no cache)}" "$BUILD_LOG" \
  $SUDO $DOCKER_COMPOSE build "${BUILD_EXTRA_FLAGS[@]}"

if $OPT_PRUNE; then
  PRUNE_LOG="${_TMPDIR}/docker_prune.log"
  run_task "Pruning dangling images" "$PRUNE_LOG" \
    $SUDO docker image prune -f
fi

echo ""
divider
echo ""
(( STEP++ ))

# ─────────────────────────────────────────────────────────────────
#  [4/4]  DOCKER DEPLOY
# ─────────────────────────────────────────────────────────────────
section "${STEP}/${TOTAL_STEPS}" "Deploying Updated System"

DEPLOY_LOG="${_TMPDIR}/docker_deploy.log"
run_task "Starting updated containers" "$DEPLOY_LOG" \
  $SUDO $DOCKER_COMPOSE up -d --remove-orphans

echo ""
divider
echo ""

# ─────────────────────────────────────────────────────────────────
#  SUCCESS SUMMARY
# ─────────────────────────────────────────────────────────────────
NEW_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)

echo ""
printf "  ${GREEN}${BOLD}"
typewriter "✓  Fetchy successfully updated!" 0.026
printf "${RESET}"
echo ""
echo -e "  ${DIM}Version:${RESET}   ${BOLD}${CYAN}${NEW_VERSION}${RESET}"
echo -e "  ${DIM}Status:${RESET}    ${GREEN}${BOLD}● Running${RESET}"
echo ""

# ── Container Status ───────────────────────────────────────────
CONTAINER_STATUS=$($SUDO $DOCKER_COMPOSE ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true)
if [[ -n "$CONTAINER_STATUS" ]]; then
  echo -e "  ${BOLD}$(c 39)Container Status:${RESET}"
  echo ""
  while IFS= read -r line; do
    echo -e "    ${DIM}${line}${RESET}"
  done <<< "$CONTAINER_STATUS"
  echo ""
fi

divider
echo ""

# ─────────────────────────────────────────────────────────────────
#  LOG COMMANDS
# ─────────────────────────────────────────────────────────────────
echo -e "  ${BOLD}${YELLOW}📋  Useful commands:${RESET}"
echo ""

_cmd_line() {
  sleep 0.06
  echo -e "  $(c 81)$1${RESET}"
  echo -e "    ${BOLD}$2${RESET}"
  echo ""
}

_cmd_line "Follow live logs:"              "$SUDO $DOCKER_COMPOSE logs -f"
_cmd_line "Show last 100 lines:"           "$SUDO $DOCKER_COMPOSE logs --tail=100"
_cmd_line "Restart the bot:"               "$SUDO $DOCKER_COMPOSE restart"
_cmd_line "Stop everything:"               "$SUDO $DOCKER_COMPOSE down"
_cmd_line "Force-rebuild without cache:"   "./update.sh --force-rebuild"
_cmd_line "Prune dangling images too:"     "./update.sh --prune"

divider
echo ""
printf "  ${DIM}Made with "
printf "${RED}❤${RESET}${DIM}  "
typewriter "by CRZX1337  •  github.com/CRZX1337/Fetchy" 0.016
printf "${RESET}\n"
echo ""
