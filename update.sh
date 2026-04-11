#!/bin/bash
set -Eeuo pipefail

# ─────────────────────────────────────────────
#  COLORS & STYLES
# ─────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
ITALIC="\033[3m"
UNDERLINE="\033[4m"

BLACK="\033[0;30m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
MAGENTA="\033[0;35m"
CYAN="\033[0;36m"
WHITE="\033[0;37m"
BRIGHT_WHITE="\033[1;37m"
BRIGHT_CYAN="\033[1;36m"
BRIGHT_BLUE="\033[1;34m"
BRIGHT_GREEN="\033[1;32m"
BRIGHT_MAGENTA="\033[1;35m"
BRIGHT_YELLOW="\033[1;33m"

# 256-color support for gradient effect
c() { printf "\033[38;5;%dm" "$1"; }

# ─────────────────────────────────────────────
#  TERMINAL SIZE
# ─────────────────────────────────────────────
TERM_WIDTH=$(tput cols 2>/dev/null || echo 80)
CENTER_OFFSET=$(( (TERM_WIDTH - 52) / 2 ))
PAD=$(printf '%*s' "$CENTER_OFFSET" '')

# ─────────────────────────────────────────────
#  ANIMATION HELPERS
# ─────────────────────────────────────────────

# Typewriter effect
typewriter() {
  local text="$1"
  local delay="${2:-0.03}"
  local i
  for (( i=0; i<${#text}; i++ )); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
  echo
}

# Animated progress bar
progress_bar() {
  local label="$1"
  local width=36
  local i
  printf "  "
  for (( i=0; i<=width; i++ )); do
    local pct=$(( i * 100 / width ))
    local filled=$(printf '%*s' "$i" '' | tr ' ' '█')
    local empty=$(printf '%*s' "$(( width - i ))" '' | tr ' ' '░')
    printf "\r  ${BRIGHT_CYAN}${filled}${DIM}${empty}${RESET}  ${BOLD}%3d%%${RESET}  ${DIM}%s${RESET}" \
      "$pct" "$label"
    sleep 0.018
  done
  echo
}

# Fade-in text (simulate by printing line with brief pause)
fade_in() {
  local text="$1"
  echo -e "${DIM}${text}${RESET}"
  sleep 0.04
  printf "\033[1A\033[2K"
  echo -e "${text}"
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
      # Cycle spinner color through cyan→blue→magenta
      local colors=("\033[1;36m" "\033[1;34m" "\033[1;35m" "\033[1;36m")
      local col="${colors[$(( i % 4 ))]}"
      printf "\r  ${col}${SPINNER_FRAMES[$i % 10]}${RESET}  ${label}..." 2>/dev/null
      i=$(( i + 1 ))
      sleep 0.07
    done
  ) &
  SPINNER_PID=$!
}

spinner_stop() {
  if [[ -n "$SPINNER_PID" ]]; then
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
    printf "\r\033[2K"
  fi
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
step_ok()   { echo -e "  ${BRIGHT_GREEN}✔${RESET}  ${BOLD}$1${RESET}"; sleep 0.05; }
step_fail() { echo -e "  ${RED}✘${RESET}  ${BOLD}$1${RESET}"; }
step_info() { echo -e "  $(c 39)ℹ${RESET}  ${DIM}$1${RESET}"; }

divider() {
  local width=$(( TERM_WIDTH < 60 ? TERM_WIDTH - 4 : 56 ))
  local line=$(printf '%*s' "$width" '' | tr ' ' '─')
  echo -e "  ${DIM}${line}${RESET}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    spinner_stop
    step_fail "Required command not found: ${BOLD}$1${RESET}"
    exit 1
  }
}

run_step() {
  local label="$1"; shift
  spinner_start "$label"
  if "$@" > /tmp/fetchy_update_log 2>&1; then
    spinner_stop
    step_ok "$label"
  else
    spinner_stop
    step_fail "$label"
    echo -e "\n${RED}${BOLD}  Error output:${RESET}"
    sed 's/^/    /' /tmp/fetchy_update_log >&2
    exit 1
  fi
}

# ─────────────────────────────────────────────
#  TRAP
# ─────────────────────────────────────────────
trap 'spinner_stop; echo -e "\n${RED}${BOLD}  ✘ Update aborted (line $LINENO).${RESET}\n" >&2' ERR

# ─────────────────────────────────────────────
#  ANIMATED BANNER
# ─────────────────────────────────────────────
clear
sleep 0.1

# Gradient banner — each row shifts color from cyan→blue
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
sleep 0.1

# Typewriter subtitle
printf "  ${DIM}"
typewriter "Your Elite Personal Media Assistant" 0.025
printf "  ${DIM}"
typewriter "── System Update Utility ──" 0.03
echo ""

divider
echo ""
sleep 0.15

# ─────────────────────────────────────────────
#  PRE-FLIGHT CHECKS
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[1/4]${RESET}  ${BRIGHT_WHITE}Pre-flight Checks${RESET}"
echo ""

require_command git
step_ok "git found"

require_command docker
step_ok "docker found"

if [ ! -f "docker-compose.yml" ]; then
  step_fail "docker-compose.yml not found — run this from the Fetchy project root"
  exit 1
fi
step_ok "docker-compose.yml found"

CURRENT_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)
step_info "Current version: ${BOLD}${CURRENT_VERSION}${RESET}"

echo ""
divider
echo ""
sleep 0.1

# ─────────────────────────────────────────────
#  GIT PULL
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[2/4]${RESET}  ${BRIGHT_WHITE}Pulling Latest Changes${RESET}"
echo ""
run_step "Syncing with remote repository" git pull --ff-only
echo ""
divider
echo ""
sleep 0.1

# ─────────────────────────────────────────────
#  DOCKER BUILD
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[3/4]${RESET}  ${BRIGHT_WHITE}Rebuilding Docker Image${RESET}"
echo ""
run_step "Building Docker infrastructure" sudo docker compose build
echo ""
divider
echo ""
sleep 0.1

# ─────────────────────────────────────────────
#  DOCKER DEPLOY
# ─────────────────────────────────────────────
echo -e "  ${BOLD}$(c 39)[4/4]${RESET}  ${BRIGHT_WHITE}Deploying Updated System${RESET}"
echo ""
run_step "Starting updated containers" sudo docker compose up -d
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  ANIMATED SUCCESS
# ─────────────────────────────────────────────
NEW_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)

# Progress bar flourish
progress_bar "Finalizing"
echo ""
sleep 0.1

# Success message with typewriter
printf "  ${BRIGHT_GREEN}${BOLD}"
typewriter "✓  Fetchy successfully updated!" 0.04
echo "${RESET}"

# Animated status lines
sleep 0.1
printf "  ${DIM}Updated to:${RESET}  "
typewriter "${BOLD}${BRIGHT_CYAN}${NEW_VERSION}${RESET}" 0.04
sleep 0.05
echo -e "  ${DIM}Status:${RESET}      ${BRIGHT_GREEN}${BOLD}● Running${RESET}"

echo ""
divider
echo ""
sleep 0.15

# ─────────────────────────────────────────────
#  LOG INFO  (fade in line by line)
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${BRIGHT_YELLOW}📋  How to view logs:${RESET}"
echo ""

_log_line() {
  sleep 0.07
  echo -e "  $(c 81)$1${RESET}"
  echo -e "      ${BOLD}$2${RESET}"
  echo ""
}

_log_line "Live logs (follow):"          "sudo docker compose logs -f"
_log_line "Last 100 lines:"               "sudo docker compose logs --tail=100"
_log_line "Specific service logs:"        "sudo docker compose logs -f fetchy"
_log_line "Container status:"             "sudo docker compose ps"

divider
echo ""
printf "  ${DIM}Made with "
printf "${RED}❤${RESET}${DIM} "
typewriter "by CRZX1337  •  github.com/CRZX1337/Fetchy" 0.018
echo ""
