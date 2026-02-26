#!/usr/bin/env bash
#
# upgrade.sh — Safe production upgrade script for Control Center
#
# Usage:
#   ./upgrade.sh [options]
#
# Options:
#   --dry-run         Preview changes without executing
#   --no-backup       Skip pre-upgrade backup (not recommended)
#   --force           Skip confirmation prompt
#   --branch <name>   Pull from specific branch (default: main)
#   --timeout <secs>  Health check timeout (default: 60)
#   --help            Show this help message
#
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

BRANCH="main"
HEALTH_TIMEOUT=60
HEALTH_INTERVAL=5
DRY_RUN=false
SKIP_BACKUP=false
FORCE=false
COMPOSE_SERVICE="web"
APP_PORT=8000
LOCK_FILE="persist/.upgrade.lock"
LOG_DIR="persist/logs"

# ─── Colors ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_FILE=""

setup_logging() {
    mkdir -p "$LOG_DIR"
    LOG_FILE="${LOG_DIR}/upgrade-$(date +%Y%m%d-%H%M%S).log"
    touch "$LOG_FILE"
}

_log() {
    local level="$1" color="$2" msg="$3"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    # Console (colored)
    echo -e "${color}[${level}]${NC} ${msg}"
    # File (plain)
    if [[ -n "$LOG_FILE" ]]; then
        echo "[${timestamp}] [${level}] ${msg}" >> "$LOG_FILE"
    fi
}

log()     { _log "INFO"    "$BLUE"   "$1"; }
warn()    { _log "WARN"    "$YELLOW" "$1"; }
error()   { _log "ERROR"   "$RED"    "$1"; }
success() { _log "OK"      "$GREEN"  "$1"; }
step()    { echo -e "\n${BOLD}${CYAN}▸ $1${NC}"; [[ -n "$LOG_FILE" ]] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] [STEP] $1" >> "$LOG_FILE"; }

# ─── State for rollback ──────────────────────────────────────────────────────

OLD_SHA=""
BACKUP_PATH=""
STASHED=false
IMAGE_TAGGED=false

# ─── Parse arguments ─────────────────────────────────────────────────────────

show_help() {
    cat <<'HELP'
upgrade.sh — Safe production upgrade script for Control Center

Usage:
  ./upgrade.sh [options]

Options:
  --dry-run         Preview changes without executing
  --no-backup       Skip pre-upgrade backup (not recommended)
  --force           Skip confirmation prompt
  --branch <name>   Pull from specific branch (default: main)
  --timeout <secs>  Health check timeout (default: 60)
  --help            Show this help message
HELP
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --no-backup)  SKIP_BACKUP=true; shift ;;
        --force)      FORCE=true; shift ;;
        --branch)     BRANCH="${2:?'--branch requires a value'}"; shift 2 ;;
        --timeout)    HEALTH_TIMEOUT="${2:?'--timeout requires a value'}"; shift 2 ;;
        --help|-h)    show_help ;;
        *)            error "Unknown option: $1"; show_help ;;
    esac
done

# ─── Cleanup trap ─────────────────────────────────────────────────────────────

cleanup() {
    local exit_code=$?
    if [[ -f "$LOCK_FILE" ]]; then
        rm -f "$LOCK_FILE"
    fi
    if [[ $exit_code -ne 0 && "$DRY_RUN" == "false" ]]; then
        echo ""
        error "Upgrade failed (exit code: $exit_code). Check log: $LOG_FILE"
    fi
    exit $exit_code
}
trap cleanup EXIT

# ─── Dry-run wrapper ─────────────────────────────────────────────────────────

run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] $*"
        return 0
    fi
    "$@"
}

# ─── Pre-flight checks ───────────────────────────────────────────────────────

preflight_checks() {
    step "Pre-flight checks"

    # docker-compose.yml exists
    if [[ ! -f "docker-compose.yml" ]]; then
        error "docker-compose.yml not found. Run this script from the project root."
        exit 1
    fi
    success "docker-compose.yml found"

    # Docker daemon running
    if ! docker info &>/dev/null; then
        error "Docker daemon is not running."
        exit 1
    fi
    success "Docker daemon running"

    # persist directories exist
    for dir in persist/data persist/media persist/backups; do
        if [[ ! -d "$dir" ]]; then
            error "Directory '$dir' not found. Is the app deployed?"
            exit 1
        fi
    done
    success "Persistent directories exist"

    # Git repo
    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        error "Not a git repository."
        exit 1
    fi
    success "Git repository detected"

    # Git remote reachable
    if ! git ls-remote --exit-code origin &>/dev/null; then
        error "Cannot reach git remote 'origin'."
        exit 1
    fi
    success "Git remote reachable"

    # Container running
    if ! docker compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .; then
        warn "No running containers detected. Backup step will be skipped if container is down."
    else
        success "Container is running"
    fi

    # Lock file
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
        error "Another upgrade is in progress (lock file exists, PID: $lock_pid)."
        error "If this is stale, remove: $LOCK_FILE"
        exit 1
    fi

    # Acquire lock
    if [[ "$DRY_RUN" == "false" ]]; then
        echo $$ > "$LOCK_FILE"
        success "Lock acquired"
    fi
}

# ─── Pre-upgrade backup ──────────────────────────────────────────────────────

create_pre_upgrade_backup() {
    step "Pre-upgrade backup"

    if [[ "$SKIP_BACKUP" == "true" ]]; then
        warn "Backup skipped (--no-backup flag)"
        return 0
    fi

    # Check if container is running
    if ! docker compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .; then
        warn "Container not running — cannot create backup via docker exec."
        warn "Proceeding without pre-upgrade backup."
        return 0
    fi

    log "Creating backup via running container..."
    local backup_output
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] docker compose exec $COMPOSE_SERVICE python manage.py backup"
        return 0
    fi

    backup_output=$(docker compose exec "$COMPOSE_SERVICE" python manage.py backup 2>&1) || {
        error "Backup command failed:"
        error "$backup_output"
        exit 1
    }

    # Extract backup path from output (format: "Backup created: /app/backups/controlcenter-backup-*.tar.gz")
    BACKUP_PATH=$(echo "$backup_output" | grep -oP '/app/backups/controlcenter-backup-[^\s]+\.tar\.gz' || true)
    if [[ -z "$BACKUP_PATH" ]]; then
        # Try alternate: the backup file is in persist/backups on the host
        local latest_backup
        latest_backup=$(ls -t persist/backups/controlcenter-backup-*.tar.gz 2>/dev/null | head -1 || true)
        if [[ -n "$latest_backup" ]]; then
            BACKUP_PATH="$latest_backup"
        else
            warn "Could not determine backup path from output, but command succeeded."
            log "Backup output: $backup_output"
            return 0
        fi
    else
        # Convert container path to host path
        BACKUP_PATH="persist/backups/$(basename "$BACKUP_PATH")"
    fi

    if [[ -n "$BACKUP_PATH" ]]; then
        local size
        size=$(du -h "$BACKUP_PATH" 2>/dev/null | cut -f1 || echo "unknown")
        success "Backup created: $BACKUP_PATH ($size)"
    fi
}

# ─── Save current state ──────────────────────────────────────────────────────

save_current_state() {
    step "Saving current state"

    OLD_SHA=$(git rev-parse HEAD)
    log "Current commit: $OLD_SHA"

    # Tag current image for rollback
    local current_image
    current_image=$(docker compose images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | head -1 || true)
    if [[ -n "$current_image" && "$current_image" != *"<none>"* ]]; then
        if [[ "$DRY_RUN" == "false" ]]; then
            local image_id
            image_id=$(docker compose images -q 2>/dev/null | head -1 || true)
            if [[ -n "$image_id" ]]; then
                docker tag "$image_id" "controlcenter:pre-upgrade" 2>/dev/null && IMAGE_TAGGED=true || true
                if [[ "$IMAGE_TAGGED" == "true" ]]; then
                    success "Tagged current image as controlcenter:pre-upgrade"
                fi
            fi
        else
            log "[DRY RUN] Would tag current image as controlcenter:pre-upgrade"
        fi
    fi

    log "Rollback point saved"
}

# ─── Pull latest code ────────────────────────────────────────────────────────

pull_latest() {
    step "Pulling latest code from origin/$BRANCH"

    run git fetch origin "$BRANCH"

    # Check if already up to date
    local local_sha remote_sha
    local_sha=$(git rev-parse HEAD)
    remote_sha=$(git rev-parse "origin/$BRANCH" 2>/dev/null || true)

    if [[ "$local_sha" == "$remote_sha" ]]; then
        success "Already up to date ($local_sha)"
        # Clean up lock and exit
        rm -f "$LOCK_FILE"
        exit 0
    fi

    # Show what's coming
    local commit_count
    commit_count=$(git rev-list --count HEAD.."origin/$BRANCH" 2>/dev/null || echo "?")
    log "Incoming: $commit_count commit(s)"
    log "  Local:  ${local_sha:0:12}"
    log "  Remote: ${remote_sha:0:12}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would merge the following commits:"
        git --no-pager log --oneline HEAD.."origin/$BRANCH" 2>/dev/null || true
        return 0
    fi

    # Stash local changes if any
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Local changes detected — stashing"
        git stash push -m "upgrade-$(date +%Y%m%d-%H%M%S)" || {
            error "Failed to stash local changes."
            exit 1
        }
        STASHED=true
        success "Changes stashed"
    fi

    # Fast-forward merge only
    git merge --ff-only "origin/$BRANCH" || {
        error "Cannot fast-forward merge. Branch has diverged."
        error "Resolve manually: git merge origin/$BRANCH"
        if [[ "$STASHED" == "true" ]]; then
            warn "Restoring stashed changes..."
            git stash pop || true
            STASHED=false
        fi
        exit 1
    }

    local new_sha
    new_sha=$(git rev-parse HEAD)
    success "Merged to ${new_sha:0:12}"

    # Restore stashed changes
    if [[ "$STASHED" == "true" ]]; then
        git stash pop || {
            warn "Could not auto-restore stashed changes."
            warn "Your changes are still in git stash. Run 'git stash pop' manually."
        }
        STASHED=false
        success "Stashed changes restored"
    fi
}

# ─── Build new image ─────────────────────────────────────────────────────────

build_image() {
    step "Building new Docker image (container still running)"

    run docker compose build || {
        error "Docker build failed."
        exit 1
    }

    success "Image built successfully"
}

# ─── Restart container ────────────────────────────────────────────────────────

restart_container() {
    step "Restarting container"

    run docker compose down || {
        error "Failed to stop container."
        exit 1
    }
    log "Container stopped"

    run docker compose up -d || {
        error "Failed to start container."
        exit 1
    }
    log "Container starting..."
}

# ─── Health check ─────────────────────────────────────────────────────────────

health_check() {
    step "Health check (timeout: ${HEALTH_TIMEOUT}s)"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would poll http://localhost:$APP_PORT/ for HTTP 200"
        return 0
    fi

    local elapsed=0
    while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
        local http_code
        http_code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${APP_PORT}/" 2>/dev/null || echo "000")

        if [[ "$http_code" =~ ^(200|301|302)$ ]]; then
            success "Application responding (HTTP $http_code) after ${elapsed}s"
            return 0
        fi

        log "Waiting... (${elapsed}s elapsed, HTTP $http_code)"
        sleep "$HEALTH_INTERVAL"
        elapsed=$((elapsed + HEALTH_INTERVAL))
    done

    # Check container logs for clues
    error "Health check failed after ${HEALTH_TIMEOUT}s"
    warn "Recent container logs:"
    docker compose logs --tail 30 2>/dev/null || true
    return 1
}

# ─── Rollback ─────────────────────────────────────────────────────────────────

rollback() {
    echo ""
    step "ROLLING BACK"

    if [[ -z "$OLD_SHA" ]]; then
        error "No rollback point saved. Manual intervention required."
        return 1
    fi

    warn "Rolling back to commit ${OLD_SHA:0:12}..."

    # Stop current container
    docker compose down 2>/dev/null || true

    # Checkout old code
    git checkout "$OLD_SHA" -- . 2>/dev/null || {
        git reset --hard "$OLD_SHA" 2>/dev/null || {
            error "Failed to restore old code. Manual intervention required."
            error "Old commit: $OLD_SHA"
            return 1
        }
    }
    log "Code restored to ${OLD_SHA:0:12}"

    # Restore backup if we have one (migration may have altered DB)
    if [[ -n "$BACKUP_PATH" && -f "$BACKUP_PATH" ]]; then
        warn "Restoring database from backup..."
        # Extract db.sqlite3 from backup to persist/data/
        local tmp_restore
        tmp_restore=$(mktemp -d)
        tar -xzf "$BACKUP_PATH" -C "$tmp_restore" 2>/dev/null || {
            error "Failed to extract backup archive."
            rm -rf "$tmp_restore"
        }
        if [[ -f "$tmp_restore/db.sqlite3" ]]; then
            cp "$tmp_restore/db.sqlite3" persist/data/db.sqlite3
            success "Database restored from backup"
        fi
        rm -rf "$tmp_restore"
    fi

    # Rebuild old image and start
    log "Rebuilding old image..."
    docker compose build 2>/dev/null || {
        error "Failed to rebuild old image."
        return 1
    }

    docker compose up -d 2>/dev/null || {
        error "Failed to restart with old image."
        return 1
    }

    # Verify rollback
    log "Verifying rollback..."
    local elapsed=0
    while [[ $elapsed -lt 30 ]]; do
        local http_code
        http_code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${APP_PORT}/" 2>/dev/null || echo "000")
        if [[ "$http_code" =~ ^(200|301|302)$ ]]; then
            success "Rollback successful — application running on ${OLD_SHA:0:12}"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    error "Rollback health check also failed. Manual intervention required."
    error "Old commit: $OLD_SHA"
    error "Backup: ${BACKUP_PATH:-none}"
    return 1
}

# ─── Confirmation prompt ──────────────────────────────────────────────────────

confirm_upgrade() {
    if [[ "$FORCE" == "true" || "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    echo ""
    echo -e "${BOLD}Upgrade Control Center?${NC}"
    echo -e "  Branch: ${CYAN}$BRANCH${NC}"
    echo -e "  Backup: ${CYAN}$(if [[ "$SKIP_BACKUP" == "true" ]]; then echo "skipped"; else echo "yes"; fi)${NC}"
    echo ""
    read -rp "Continue? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) log "Upgrade cancelled."; exit 0 ;;
    esac
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
    echo -e "${BOLD}${CYAN}"
    echo "╔═══════════════════════════════════════╗"
    echo "║     Control Center — Upgrade Tool     ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}[DRY RUN MODE — no changes will be made]${NC}"
        echo ""
    fi

    setup_logging
    log "Log file: $LOG_FILE"

    preflight_checks
    confirm_upgrade
    save_current_state
    create_pre_upgrade_backup

    pull_latest

    build_image

    restart_container

    if ! health_check; then
        error "Upgrade failed — initiating rollback"
        rollback
        exit 1
    fi

    # ─── Success summary ──────────────────────────────────────────────────

    local new_sha
    new_sha=$(git rev-parse HEAD)

    echo ""
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════╗"
    echo "║         Upgrade Complete!             ║"
    echo -e "╚═══════════════════════════════════════╝${NC}"
    echo ""
    success "Commit: ${OLD_SHA:0:12} → ${new_sha:0:12}"
    success "Branch: $BRANCH"
    if [[ -n "$BACKUP_PATH" ]]; then
        success "Backup: $BACKUP_PATH"
    fi
    success "Log: $LOG_FILE"
    echo ""

    # Offer to prune old Docker images
    local dangling
    dangling=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$dangling" -gt 0 ]]; then
        log "$dangling dangling Docker image(s) found. Clean up with: docker image prune -f"
    fi
}

main "$@"
