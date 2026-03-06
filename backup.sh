#!/usr/bin/env bash
#
# backup.sh — Restic-based snapshot utility for Control Center
#
# Takes filesystem-level snapshots of the entire application directory
# for bulletproof backup and restore. Includes code, data, config, and media.
#
# Usage:
#   ./backup.sh [command] [options]
#
# Commands:
#   install           Download restic binary to ./bin/restic
#   init              Initialize restic repository (first-time setup)
#   snapshot          Create a snapshot (default if no command given)
#   list              List all snapshots
#   restore <id>      Restore snapshot (stops Docker, restores, restarts)
#   restore latest    Restore most recent snapshot
#   prune             Remove old snapshots per retention policy
#   diff <id1> <id2>  Show differences between two snapshots
#   check             Verify repository integrity
#   stats             Show repository disk usage
#
# Options:
#   --tag <name>      Add custom tag to snapshot (default: "manual")
#   --keep <n>        Override retention count (default: 10)
#   --dry-run         Preview without executing
#   --help            Show help
#
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
EXCLUDE_FILE="${APP_DIR}/.restic-exclude"
RESTIC_BIN="${APP_DIR}/bin/restic"

# Restic config — defaults applied after .env loading (see below)
DEFAULT_TAG="manual"

# Runtime flags
DRY_RUN=false
CUSTOM_TAG=""
CUSTOM_KEEP=""

# ─── Colors ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Logging ──────────────────────────────────────────────────────────────────

log()     { echo -e "${BLUE}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
step()    { echo -e "\n${BOLD}${CYAN}▸ $1${NC}"; }

# ─── Help ─────────────────────────────────────────────────────────────────────

show_help() {
    cat <<'HELP'
backup.sh — Restic-based snapshot utility for Control Center

Usage:
  ./backup.sh [command] [options]

Commands:
  install           Download restic binary to ./bin/restic
  init              Initialize restic repository (first-time setup)
  snapshot          Create a snapshot (default if no command given)
  list              List all snapshots
  restore <id>      Restore snapshot (stops Docker, restores, restarts)
  restore latest    Restore most recent snapshot
  prune             Remove old snapshots per retention policy
  diff <id1> <id2>  Show differences between two snapshots
  check             Verify repository integrity
  stats             Show repository disk usage

Options:
  --tag <name>      Add custom tag to snapshot (default: "manual")
  --keep <n>        Override retention count (default: 10)
  --dry-run         Preview without executing
  --help            Show help

Environment Variables:
  RESTIC_REPOSITORY     Repository path (default: /opt/backups/control-center)
  RESTIC_PASSWORD       Repository password (required)
  RESTIC_PASSWORD_FILE  Alternative: path to file containing password
  RESTIC_KEEP_LAST      Default retention count (default: 10)

First-Time Setup:
  1. ./backup.sh install
  2. Add to .env: RESTIC_PASSWORD="your-secure-password"
  3. ./backup.sh init
  4. ./backup.sh snapshot
HELP
    exit 0
}

# ─── Restic binary resolution ─────────────────────────────────────────────────

_resolve_restic_bin() {
    # Prefer local bin/restic, fall back to system restic
    if [[ -x "$RESTIC_BIN" ]]; then
        return 0
    fi
    # Search PATH for a real binary (not our shell function)
    local system_restic
    system_restic="$(command -p env which restic 2>/dev/null || true)"
    if [[ -n "$system_restic" && -x "$system_restic" ]]; then
        RESTIC_BIN="$system_restic"
        return 0
    fi
    return 1
}

restic() {
    "$RESTIC_BIN" "$@"
}

_detect_platform() {
    local os arch
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        arm64)   arch="arm64" ;;
        *)       error "Unsupported architecture: $arch"; exit 1 ;;
    esac
    echo "${os}_${arch}"
}

cmd_install() {
    step "Installing restic binary"

    if [[ -x "$RESTIC_BIN" ]]; then
        local current_version
        current_version=$("$RESTIC_BIN" version 2>/dev/null | awk '{print $2}' || echo "unknown")
        log "Existing restic found: $current_version"
    fi

    log "Fetching latest release from GitHub..."
    local latest_tag latest_version
    latest_tag=$(curl -sI https://github.com/restic/restic/releases/latest \
        | grep -i '^location:' | sed 's/.*tag\///' | tr -d '[:space:]')

    if [[ -z "$latest_tag" ]]; then
        error "Failed to determine latest restic release."
        exit 1
    fi

    latest_version="${latest_tag#v}"
    log "Latest version: $latest_version"

    local platform
    platform=$(_detect_platform)
    local url="https://github.com/restic/restic/releases/download/${latest_tag}/restic_${latest_version}_${platform}.bz2"
    log "Downloading: $url"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would download restic $latest_version to $RESTIC_BIN"
        return 0
    fi

    mkdir -p "$(dirname "$RESTIC_BIN")"

    curl -sL "$url" | bunzip2 > "$RESTIC_BIN" || {
        error "Download failed. URL: $url"
        rm -f "$RESTIC_BIN"
        exit 1
    }

    chmod +x "$RESTIC_BIN"

    local installed_version
    installed_version=$("$RESTIC_BIN" version 2>/dev/null || echo "unknown")
    success "Installed: $installed_version"
    success "Binary: $RESTIC_BIN"
}

# ─── Preflight ────────────────────────────────────────────────────────────────

check_restic() {
    if ! _resolve_restic_bin; then
        error "restic binary not found at $RESTIC_BIN"
        error "Install with: ./backup.sh install"
        exit 1
    fi
}

check_password() {
    if [[ -z "${RESTIC_PASSWORD:-}" && -z "${RESTIC_PASSWORD_FILE:-}" ]]; then
        error "RESTIC_PASSWORD or RESTIC_PASSWORD_FILE must be set."
        error "Set it in your .env file or shell environment."
        exit 1
    fi
}

check_repo() {
    check_restic
    check_password
    if ! restic cat config &>/dev/null; then
        error "Restic repository not found or inaccessible at: $RESTIC_REPOSITORY"
        error "Run './backup.sh init' to create it, or check RESTIC_REPOSITORY path."
        exit 1
    fi
}

get_git_sha() {
    if git -C "$APP_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
        git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# ─── Docker helpers ───────────────────────────────────────────────────────────

is_container_running() {
    docker compose -f "${APP_DIR}/docker-compose.yml" ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .
}

stop_container() {
    if is_container_running; then
        log "Stopping Docker container for data consistency..."
        docker compose -f "${APP_DIR}/docker-compose.yml" down 2>/dev/null || {
            warn "Failed to stop container gracefully."
        }
        success "Container stopped"
    else
        log "Container not running (skip stop)"
    fi
}

start_container() {
    log "Starting Docker container..."
    docker compose -f "${APP_DIR}/docker-compose.yml" up -d 2>/dev/null || {
        error "Failed to start container."
        return 1
    }
    success "Container started"
}

# ─── Commands ─────────────────────────────────────────────────────────────────

cmd_init() {
    step "Initializing restic repository"
    check_restic
    check_password

    if restic cat config &>/dev/null; then
        warn "Repository already exists at: $RESTIC_REPOSITORY"
        success "Nothing to do"
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would create restic repository at: $RESTIC_REPOSITORY"
        return 0
    fi

    mkdir -p "$(dirname "$RESTIC_REPOSITORY")"
    restic init || {
        error "Failed to initialize restic repository."
        exit 1
    }

    success "Repository initialized at: $RESTIC_REPOSITORY"
    echo ""
    log "IMPORTANT: Save your RESTIC_PASSWORD somewhere safe."
    log "Without it, snapshots are unrecoverable."
}

cmd_snapshot() {
    local tag="${CUSTOM_TAG:-$DEFAULT_TAG}"
    local sha
    sha=$(get_git_sha)

    step "Creating restic snapshot"
    check_repo

    log "Repository: $RESTIC_REPOSITORY"
    log "Source: $APP_DIR"
    log "Tag: $tag"
    log "Git SHA: $sha"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would stop container, snapshot $APP_DIR, restart container"
        log "[DRY RUN] Tags: $tag, sha:$sha"
        return 0
    fi

    local was_running=false
    if is_container_running; then
        was_running=true
    fi

    # Stop container for SQLite consistency
    stop_container

    # Build exclude args
    local exclude_args=()
    if [[ -f "$EXCLUDE_FILE" ]]; then
        exclude_args=(--exclude-file "$EXCLUDE_FILE")
    fi

    # Take snapshot
    log "Taking snapshot..."
    restic backup "$APP_DIR" \
        "${exclude_args[@]}" \
        --tag "$tag" \
        --tag "sha:$sha" \
        --one-file-system || {
        error "Snapshot failed!"
        # Restart container even on failure
        if [[ "$was_running" == "true" ]]; then
            start_container
        fi
        exit 1
    }

    # Restart container
    if [[ "$was_running" == "true" ]]; then
        start_container
    fi

    success "Snapshot created successfully"

    # Show latest snapshot info
    echo ""
    restic snapshots --latest 1 --compact
}

cmd_list() {
    step "Listing snapshots"
    check_repo

    restic snapshots --compact
}

cmd_restore() {
    local snapshot_id="${1:-}"

    if [[ -z "$snapshot_id" ]]; then
        error "Usage: ./backup.sh restore <snapshot-id|latest>"
        exit 1
    fi

    step "Restoring snapshot: $snapshot_id"
    check_repo

    # Show what we're restoring
    if [[ "$snapshot_id" != "latest" ]]; then
        restic snapshots "$snapshot_id" --compact 2>/dev/null || {
            error "Snapshot '$snapshot_id' not found."
            exit 1
        }
    else
        log "Restoring most recent snapshot:"
        restic snapshots --latest 1 --compact
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would stop container, restore snapshot $snapshot_id, restart container"
        return 0
    fi

    echo ""
    echo -e "${BOLD}${YELLOW}WARNING: This will overwrite all files in $APP_DIR${NC}"
    echo -e "${YELLOW}Including: code, database, config (.env), media${NC}"
    echo ""
    read -rp "Continue with restore? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY]) ;;
        *) log "Restore cancelled."; exit 0 ;;
    esac

    # Stop container
    stop_container

    # Perform restore
    # --delete removes files in APP_DIR that aren't in the snapshot
    # --include scopes the delete to just our app directory (required by restic)
    log "Restoring files to $APP_DIR..."
    local restore_output
    restore_output=$(restic restore "$snapshot_id" --target / \
        --delete --include "$APP_DIR" 2>&1) || {
        # Restic may report non-fatal errors (e.g., can't chmod parent dirs like /tmp)
        # Check if files were actually restored by looking for the summary line
        if echo "$restore_output" | grep -q "Summary:.*Restored"; then
            warn "Restore completed with non-fatal errors (likely parent directory permissions)."
            log "$restore_output"
        else
            error "Restore failed!"
            error "$restore_output"
            error "Container is stopped. Manual intervention required."
            exit 1
        fi
    }

    success "Files restored"

    # Start container (entrypoint.sh handles migrate + collectstatic)
    start_container

    success "Restore complete"
}

cmd_prune() {
    local keep="${CUSTOM_KEEP:-$KEEP_LAST}"

    step "Pruning old snapshots (keeping last $keep)"
    check_repo

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would run: restic forget --keep-last $keep --prune"
        restic forget --keep-last "$keep" --dry-run --compact
        return 0
    fi

    restic forget --keep-last "$keep" --prune --compact || {
        error "Prune failed."
        exit 1
    }

    success "Pruned old snapshots (kept last $keep)"
}

cmd_diff() {
    local id1="${1:-}" id2="${2:-}"

    if [[ -z "$id1" || -z "$id2" ]]; then
        error "Usage: ./backup.sh diff <snapshot-id-1> <snapshot-id-2>"
        exit 1
    fi

    step "Comparing snapshots: $id1 vs $id2"
    check_repo

    restic diff "$id1" "$id2"
}

cmd_check() {
    step "Verifying repository integrity"
    check_repo

    restic check || {
        error "Repository integrity check failed!"
        exit 1
    }

    success "Repository is healthy"
}

cmd_stats() {
    step "Repository statistics"
    check_repo

    restic stats
    echo ""
    restic stats --mode raw-data
}

# ─── Parse arguments ──────────────────────────────────────────────────────────

COMMAND="snapshot"  # default command
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        install|init|snapshot|list|restore|prune|diff|check|stats)
            COMMAND="$1"
            shift
            ;;
        --tag)
            CUSTOM_TAG="${2:?'--tag requires a value'}"
            shift 2
            ;;
        --keep)
            CUSTOM_KEEP="${2:?'--keep requires a value'}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        -*)
            error "Unknown option: $1"
            show_help
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

# ─── Load .env and apply defaults ────────────────────────────────────────────

if [[ -f "${APP_DIR}/.env" ]]; then
    # Source only RESTIC_* vars from .env (don't clobber existing env)
    while IFS='=' read -r key value; do
        key=$(echo "$key" | xargs)  # trim whitespace
        case "$key" in
            RESTIC_REPOSITORY|RESTIC_PASSWORD|RESTIC_PASSWORD_FILE|RESTIC_KEEP_LAST)
                if [[ -z "${!key:-}" ]]; then
                    export "$key"="$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
                fi
                ;;
        esac
    done < <(grep -E '^RESTIC_' "${APP_DIR}/.env" 2>/dev/null || true)
fi

# Apply defaults after .env load
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/opt/backups/control-center}"
export RESTIC_REPOSITORY
KEEP_LAST="${RESTIC_KEEP_LAST:-10}"

# ─── Banner ───────────────────────────────────────────────────────────────────

echo -e "${BOLD}${CYAN}"
echo "╔═══════════════════════════════════════╗"
echo "║   Control Center — Backup Utility     ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}[DRY RUN MODE — no changes will be made]${NC}"
    echo ""
fi

# ─── Dispatch ─────────────────────────────────────────────────────────────────

case "$COMMAND" in
    install)    cmd_install ;;
    init)       cmd_init ;;
    snapshot)   cmd_snapshot ;;
    list)       cmd_list ;;
    restore)    cmd_restore "${POSITIONAL_ARGS[0]:-}" ;;
    prune)      cmd_prune ;;
    diff)       cmd_diff "${POSITIONAL_ARGS[0]:-}" "${POSITIONAL_ARGS[1]:-}" ;;
    check)      cmd_check ;;
    stats)      cmd_stats ;;
    *)          error "Unknown command: $COMMAND"; show_help ;;
esac
