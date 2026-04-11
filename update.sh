#!/bin/bash
set -Eeuo pipefail

# ─────────────────────────────────────────────
#  COLORS & STYLES
# ─────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
BRIGHT_WHITE="\033[1;37m"
BRIGHT_CYAN="\033[1;36m"
BRIGHT_GREEN="\033[1;32m"
BRIGHT_YELLOW="\033[1;33m"

c() { printf "\033[38;5;%dm" "$1"; }

TERM_WIDTH=$(tput cols 2>/dev/null || echo 80)

# ─────────────────────────────────────────────
#  ANIMATION HELPERS
# ─────────────────────────────────────────────
typewriter() {
  local text="$1" delay="${2:-0.03}" i
  for (( i=0; i<${#text}; i++ )); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
  echo
}

progress_bar() {
  local label="$1" width=36 i
  for (( i=0; i<=width; i++ )); do
    local pct=$(( i * 100 / width ))
    local filled=$(printf '%*s' "$i" '' | tr ' ' '█')
    local empty=$(printf '%*s' "$(( width - i ))" '' | tr ' ' '░')
    printf "\r  ${BRIGHT_CYAN}%s${DIM}%s${RESET}  ${BOLD}%3d%%${RESET}  ${DIM}%s${RESET}" \
      "$filled" "$empty" "$pct" "$label"
    sleep 0.018
  done
  echo
}

divider() {
  local width=$(( TERM_WIDTH < 60 ? TERM_WIDTH - 4 : 56 ))
  echo -e "  ${DIM}$(printf '%*s' "$width" '' | tr ' ' '─')${RESET}"
}

step_ok()   { echo -e "  ${BRIGHT_GREEN}✔${RESET}  ${BOLD}$1${RESET}"; }
step_fail() { echo -e "  ${RED}✘${RESET}  ${BOLD}$1${RESET}"; }
step_info() { echo -e "  $(c 39)ℹ${RESET}  ${DIM}$1${RESET}"; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || { step_fail "Required: $1 not found"; exit 1; }
}

# ─────────────────────────────────────────────
#  SPINNER
# ─────────────────────────────────────────────
SPINNER_PID=""
SPINNER_FRAMES=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")

spinner_start() {
  local label="$1"
  (
    local i=0
    while true; do
      local colors=("\033[1;36m" "\033[1;34m" "\033[1;35m" "\033[1;36m")
      printf "\r  ${colors[$(( i % 4 ))]}${SPINNER_FRAMES[$((i % 10))]}${RESET}  %s..." "$label" 2>/dev/null
      i=$(( i + 1 ))
      sleep 0.07
    done
  ) &
  SPINNER_PID=$!
}

spinner_stop() {
  [[ -n "$SPINNER_PID" ]] || return 0
  kill "$SPINNER_PID" 2>/dev/null
  wait "$SPINNER_PID" 2>/dev/null || true
  SPINNER_PID=""
  printf "\r\033[2K"
}

# ─────────────────────────────────────────────
#  BACKGROUND RUNNER
# ─────────────────────────────────────────────
BG_LOG="/tmp/fetchy_bg_$$.log"
BG_STATUS="/tmp/fetchy_status_$$"
mkdir -p "$BG_STATUS"

bg_run() {
  local name="$1"; shift
  (
    if "$@" >> "$BG_LOG" 2>&1; then
      touch "${BG_STATUS}/${name}.ok"
    else
      echo "$?" > "${BG_STATUS}/${name}.fail"
    fi
  ) &
  echo $!
}

bg_wait() {
  local name="$1" pid="$2" label="$3"
  spinner_start "$label"
  wait "$pid" 2>/dev/null || true
  spinner_stop
  if [[ -f "${BG_STATUS}/${name}.fail" ]]; then
    step_fail "$label"
    echo -e "\n${RED}${BOLD}  Error output:${RESET}"
    sed 's/^/    /' "$BG_LOG" >&2
    exit 1
  fi
  step_ok "$label"
}

# ─────────────────────────────────────────────
#  CHANGELOG DISPLAY
#  Shows commits pulled since BEFORE_SHA.
#  Categories derived from conventional commit prefixes.
# ─────────────────────────────────────────────
show_changelog() {
  local before_sha="$1"
  local after_sha
  after_sha=$(git rev-parse HEAD)

  if [[ "$before_sha" == "$after_sha" ]]; then
    echo -e "  ${DIM}Already up to date — no new commits.${RESET}"
    echo ""
    return
  fi

  # Collect new commits: hash|subject
  local commits
  commits=$(git log --pretty=format:"%h|⁠%s" "${before_sha}..${after_sha}" 2>/dev/null || true)

  if [[ -z "$commits" ]]; then
    echo -e "  ${DIM}No commit details available.${RESET}"
    echo ""
    return
  fi

  local count
  count=$(echo "$commits" | wc -l | tr -d ' ')

  echo -e "  ${BOLD}$(c 39)ℹ${RESET}  ${BOLD}${count} new commit$([ "$count" -ne 1 ] && echo 's' || true) pulled:${RESET}"
  echo ""

  while IFS='|' read -r hash subject; do
    # Strip zero-width joiner we used as delimiter guard
    subject="${subject//$'\u2060'/}"
    local icon color
    # Assign icon + color by conventional commit prefix
    case "$subject" in
      feat*|feature*)   icon="✨" ; color="$(c 84)"  ;;
      fix*|bugfix*)     icon="🐛" ; color="$(c 203)" ;;
      docs*)            icon="📖" ; color="$(c 75)"  ;;
      refactor*)        icon="♻️ " ; color="$(c 141)" ;;
      perf*)            icon="⚡" ; color="$(c 214)" ;;
      chore*|ci*|build*)icon="🔧" ; color="$(c 245)" ;;
      test*)            icon="🧪" ; color="$(c 111)" ;;
      style*)           icon="🎨" ; color="$(c 219)" ;;
      revert*)          icon="⏪" ; color="$(c 196)" ;;
      *)                icon="▸"  ; color="$(c 252)" ;;
    esac

    # Truncate subject if too long
    local max_len=$(( TERM_WIDTH - 18 ))
    if (( ${#subject} > max_len )); then
      subject="${subject:0:$max_len}…"
    fi

    printf "  ${DIM}%s${RESET}  %s ${color}%s${RESET}\n" \
      "$hash" "$icon" "$subject"
    sleep 0.05
  done <<< "$commits"

  echo ""
}

# ─────────────────────────────────────────────
#  CLEANUP ON EXIT
# ─────────────────────────────────────────────
cleanup() {
  spinner_stop
  rm -f "$BG_LOG"
  rm -rf "$BG_STATUS"
}
trap 'cleanup; echo -e "\n${RED}${BOLD}  ✘ Update aborted (line $LINENO).${RESET}\n" >&2' ERR
trap 'cleanup' EXIT

# ─────────────────────────────────────────────
#  ANIMATED BANNER
# ─────────────────────────────────────────────
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
  sleep 0.06
done
echo ""
printf "  ${DIM}"
typewriter "Your Elite Personal Media Assistant" 0.025
printf "  ${DIM}"
typewriter "── System Update Utility ──" 0.03
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  [1/4]  PRE-FLIGHT
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[1/4]${RESET}  ${BRIGHT_WHITE}Pre-flight Checks${RESET}"
echo ""

require_command git
step_ok "git found"
require_command docker
step_ok "docker found"

if [ ! -f "docker-compose.yml" ]; then
  step_fail "docker-compose.yml not found — run from the Fetchy project root"
  exit 1
fi
step_ok "docker-compose.yml found"

CURRENT_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)
# Save SHA BEFORE pull so we can diff later
BEFORE_SHA=$(git rev-parse HEAD)
step_info "Current version: ${BOLD}${CURRENT_VERSION}${RESET}"

echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  [2/4]  GIT PULL
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[2/4]${RESET}  ${BRIGHT_WHITE}Pulling Latest Changes${RESET}"
echo ""

GIT_PID=$(bg_run "git_pull" git pull --ff-only)

printf "  ${DIM}"
typewriter "Contacting remote repository..." 0.03
printf "  ${DIM}"
typewriter "Checking for new commits..." 0.025
printf "  ${DIM}"
typewriter "Verifying integrity..." 0.03

bg_wait "git_pull" "$GIT_PID" "Syncing with remote repository"
echo ""

# ——— CHANGELOG: show what just got pulled ———
show_changelog "$BEFORE_SHA"

divider
echo ""

# ─────────────────────────────────────────────
#  [3/4]  DOCKER BUILD
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[3/4]${RESET}  ${BRIGHT_WHITE}Rebuilding Docker Image${RESET}"
echo ""

BUILD_PID=$(bg_run "docker_build" sudo docker compose build)

printf "  ${DIM}"
typewriter "Pulling base layers..." 0.04
printf "  ${DIM}"
typewriter "Resolving dependencies..." 0.035
printf "  ${DIM}"
typewriter "Compiling image filesystem..." 0.03
printf "  ${DIM}"
typewriter "Applying patches..." 0.04
printf "  ${DIM}"
typewriter "Optimising layer cache..." 0.03

bg_wait "docker_build" "$BUILD_PID" "Building Docker infrastructure"
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  [4/4]  DOCKER DEPLOY
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[4/4]${RESET}  ${BRIGHT_WHITE}Deploying Updated System${RESET}"
echo ""

DEPLOY_PID=$(bg_run "docker_deploy" sudo docker compose up -d)

printf "  ${DIM}"
typewriter "Stopping old containers..." 0.04
printf "  ${DIM}"
typewriter "Mounting volumes..." 0.035
printf "  ${DIM}"
typewriter "Starting new containers..." 0.04

bg_wait "docker_deploy" "$DEPLOY_PID" "Starting updated containers"
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  SUCCESS
# ─────────────────────────────────────────────
NEW_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)

progress_bar "Finalizing"
echo ""

printf "  ${BRIGHT_GREEN}${BOLD}"
typewriter "✓  Fetchy successfully updated!" 0.04
echo "${RESET}"

sleep 0.1
printf "  ${DIM}Updated to:${RESET}  "
typewriter "${BOLD}${BRIGHT_CYAN}${NEW_VERSION}${RESET}" 0.04
echo -e "  ${DIM}Status:${RESET}      ${BRIGHT_GREEN}${BOLD}● Running${RESET}"

echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  LOG INFO
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${BRIGHT_YELLOW}📋  How to view logs:${RESET}"
echo ""

_log_line() {
  sleep 0.07
  echo -e "  $(c 81)$1${RESET}"
  echo -e "      ${BOLD}$2${RESET}"
  echo ""
}

_log_line "Live logs (follow):"       "sudo docker compose logs -f"
_log_line "Last 100 lines:"            "sudo docker compose logs --tail=100"
_log_line "Specific service logs:"     "sudo docker compose logs -f fetchy"
_log_line "Container status:"          "sudo docker compose ps"

divider
echo ""
printf "  ${DIM}Made with "
printf "${RED}❤${RESET}${DIM} "
typewriter "by CRZX1337  •  github.com/CRZX1337/Fetchy" 0.018
echo ""
