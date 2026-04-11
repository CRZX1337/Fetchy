#!/bin/bash
set -Eeuo pipefail

# ─────────────────────────────────────────────
#  COLORS & STYLES
# ─────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"

BLACK="\033[0;30m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
MAGENTA="\033[0;35m"
CYAN="\033[0;36m"
WHITE="\033[0;37m"

BG_BLACK="\033[40m"
BG_BLUE="\033[44m"

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
      printf "\r  ${CYAN}${SPINNER_FRAMES[$i]}${RESET}  ${label}..." 2>/dev/null
      i=$(( (i + 1) % ${#SPINNER_FRAMES[@]} ))
      sleep 0.08
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
step_ok()   { echo -e "  ${GREEN}✔${RESET}  ${BOLD}$1${RESET}"; }
step_fail() { echo -e "  ${RED}✘${RESET}  ${BOLD}$1${RESET}"; }
step_info() { echo -e "  ${CYAN}ℹ${RESET}  ${DIM}$1${RESET}"; }
divider()   { echo -e "${DIM}  ───────────────────────────────────────────${RESET}"; }

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
#  BANNER
# ─────────────────────────────────────────────
clear
echo ""
echo -e "${BOLD}${CYAN}  ███████╗███████╗████████╗ ██████╗██╗  ██╗██╗   ██╗${RESET}"
echo -e "${BOLD}${CYAN}  ██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║╚██╗ ██╔╝${RESET}"
echo -e "${BOLD}${CYAN}  █████╗  █████╗     ██║   ██║     ███████║ ╚████╔╝ ${RESET}"
echo -e "${BOLD}${CYAN}  ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║  ╚██╔╝  ${RESET}"
echo -e "${BOLD}${CYAN}  ██║     ███████╗   ██║   ╚██████╗██║  ██║   ██║   ${RESET}"
echo -e "${BOLD}${CYAN}  ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝   ╚═╝  ${RESET}"
echo ""
echo -e "${DIM}             Your Elite Personal Media Assistant${RESET}"
echo -e "${DIM}             ── System Update Utility ──${RESET}"
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  PRE-FLIGHT CHECKS
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${WHITE}[1/4]  Pre-flight Checks${RESET}"
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

# ─────────────────────────────────────────────
#  GIT PULL
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${WHITE}[2/4]  Pulling Latest Changes${RESET}"
echo ""
run_step "Syncing with remote repository" git pull --ff-only
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  DOCKER BUILD
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${WHITE}[3/4]  Rebuilding Docker Image${RESET}"
echo ""
run_step "Building Docker infrastructure" sudo docker compose build
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  DOCKER DEPLOY
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${WHITE}[4/4]  Deploying Updated System${RESET}"
echo ""
run_step "Starting updated containers" sudo docker compose up -d
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  SUCCESS
# ─────────────────────────────────────────────
NEW_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)

echo -e "  ${GREEN}${BOLD}🎉  Fetchy successfully updated!${RESET}"
echo ""
echo -e "  ${DIM}Updated to:${RESET}  ${BOLD}${CYAN}${NEW_VERSION}${RESET}"
echo -e "  ${DIM}Status:${RESET}      ${GREEN}${BOLD}● Running${RESET}"
echo ""
divider
echo ""

# ─────────────────────────────────────────────
#  LOG INFO
# ─────────────────────────────────────────────
echo -e "  ${BOLD}${YELLOW}📋  How to view logs:${RESET}"
echo ""
echo -e "  ${CYAN}Live logs (follow):${RESET}"
echo -e "  ${BOLD}    sudo docker compose logs -f${RESET}"
echo ""
echo -e "  ${CYAN}Last 100 lines:${RESET}"
echo -e "  ${BOLD}    sudo docker compose logs --tail=100${RESET}"
echo ""
echo -e "  ${CYAN}Specific service logs:${RESET}"
echo -e "  ${BOLD}    sudo docker compose logs -f fetchy${RESET}"
echo ""
echo -e "  ${CYAN}Container status:${RESET}"
echo -e "  ${BOLD}    sudo docker compose ps${RESET}"
echo ""
divider
echo ""
echo -e "  ${DIM}Made with ❤️  by CRZX1337  •  github.com/CRZX1337/Fetchy${RESET}"
echo ""
