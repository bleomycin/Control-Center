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
#   --no-restic       Fall back to Django backup (skip restic snapshot)
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
NO_RESTIC=false
FORCE=false
COMPOSE_SERVICE="web"
APP_PORT=8000
LOCK_FILE="persist/.upgrade.lock"
LOG_DIR="persist/logs"
EXCLUDE_FILE=".restic-exclude"
RESTIC_BIN="./bin/restic"
RESTIC_AVAILABLE=false

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
RESTIC_SNAPSHOT_ID=""
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
  --no-restic       Fall back to Django backup (skip restic snapshot)
  --force           Skip confirmation prompt
  --branch <name>   Pull from specific branch (default: main)
  --timeout <secs>  Health check timeout (default: 60)
  --help            Show this help message

Backup Strategy:
  By default, a restic filesystem snapshot is taken before upgrading.
  This captures code, data, config (.env), and media in one snapshot.
  Use --no-restic to fall back to the Django-level backup (SQLite + media only).
  Setup: ./backup.sh install && add RESTIC_PASSWORD to .env && ./backup.sh init
HELP
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --no-backup)  SKIP_BACKUP=true; shift ;;
        --no-restic)  NO_RESTIC=true; shift ;;
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

# ─── Load .env for restic config ─────────────────────────────────────────────

load_restic_env() {
    if [[ -f .env ]]; then
        while IFS='=' read -r key value; do
            key=$(echo "$key" | xargs)
            case "$key" in
                RESTIC_REPOSITORY|RESTIC_PASSWORD|RESTIC_PASSWORD_FILE|RESTIC_KEEP_LAST)
                    if [[ -z "${!key:-}" ]]; then
                        export "$key"="$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
                    fi
                    ;;
            esac
        done < <(grep -E '^RESTIC_' .env 2>/dev/null || true)
    fi
    # Apply defaults
    RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/opt/docker-backups/control-center}"
    export RESTIC_REPOSITORY
}

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

detect_restic() {
    if [[ "$NO_RESTIC" == "true" ]]; then
        RESTIC_AVAILABLE=false
        return
    fi
    load_restic_env
    if ! _resolve_restic_bin; then
        RESTIC_AVAILABLE=false
        return
    fi
    if [[ -z "${RESTIC_PASSWORD:-}" && -z "${RESTIC_PASSWORD_FILE:-}" ]]; then
        RESTIC_AVAILABLE=false
        return
    fi
    if ! restic cat config &>/dev/null; then
        RESTIC_AVAILABLE=false
        return
    fi
    RESTIC_AVAILABLE=true
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

    # Restic availability
    detect_restic
    if [[ "$RESTIC_AVAILABLE" == "true" ]]; then
        success "Restic available (repository: $RESTIC_REPOSITORY)"
    elif [[ "$NO_RESTIC" == "true" ]]; then
        log "Restic disabled (--no-restic flag)"
    elif [[ "$SKIP_BACKUP" != "true" ]]; then
        warn "Restic not available — falling back to Django backup"
        if ! _resolve_restic_bin; then
            warn "  restic binary not found (install with: ./backup.sh install)"
        elif [[ -z "${RESTIC_PASSWORD:-}" && -z "${RESTIC_PASSWORD_FILE:-}" ]]; then
            warn "  RESTIC_PASSWORD not set (add to .env)"
        else
            warn "  Repository not initialized (run: ./backup.sh init)"
        fi
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

    if [[ "$RESTIC_AVAILABLE" == "true" ]]; then
        _restic_snapshot
    else
        _django_backup
    fi
}

_restic_snapshot() {
    local sha
    sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    log "Creating restic snapshot (tagged: upgrade, sha:$sha)..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would stop container, take restic snapshot, restart container"
        return 0
    fi

    # Stop container for SQLite consistency
    docker compose down 2>/dev/null || true
    log "Container stopped for snapshot"

    # Build exclude args
    local exclude_args=()
    if [[ -f "$EXCLUDE_FILE" ]]; then
        exclude_args=(--exclude-file "$EXCLUDE_FILE")
    fi

    # Take snapshot
    local snapshot_output
    snapshot_output=$(restic backup . \
        "${exclude_args[@]}" \
        --tag "upgrade" \
        --tag "sha:$sha" \
        --one-file-system 2>&1) || {
        error "Restic snapshot failed!"
        error "$snapshot_output"
        # Restart container even on failure
        docker compose up -d 2>/dev/null || true
        exit 1
    }

    # Extract snapshot ID from output
    RESTIC_SNAPSHOT_ID=$(echo "$snapshot_output" | sed -n 's/.*snapshot \([a-f0-9]\{1,\}\).*/\1/p' | tail -1 || true)

    success "Restic snapshot created${RESTIC_SNAPSHOT_ID:+ ($RESTIC_SNAPSHOT_ID)}"
    log "Snapshot output: $(echo "$snapshot_output" | tail -3)"

    # Container stays down — it will be rebuilt and restarted later
}

_django_backup() {
    # Fallback: Django-level backup (SQLite + media in .tar.gz)
    # Check if container is running
    if ! docker compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .; then
        warn "Container not running — cannot create Django backup via docker exec."
        warn "Proceeding without pre-upgrade backup."
        return 0
    fi

    log "Creating Django backup via running container..."
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
    BACKUP_PATH=$(echo "$backup_output" | sed -n 's|.*\(/app/backups/controlcenter-backup-[^ ]*\.tar\.gz\).*|\1|p' | tail -1 || true)
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
        success "Django backup created: $BACKUP_PATH ($size)"
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

    # Fast-forward merge, with fallback for force-pushed (rewritten) history
    if ! git merge --ff-only "origin/$BRANCH" 2>/dev/null; then
        # Check if remote history was rewritten (force push) — local HEAD
        # is not an ancestor of the remote, meaning history diverged
        if ! git merge-base --is-ancestor HEAD "origin/$BRANCH" 2>/dev/null; then
            warn "Remote history was rewritten (force push detected)."
            warn "Resetting local branch to match origin/$BRANCH."
            git reset --hard "origin/$BRANCH" || {
                error "Failed to reset to origin/$BRANCH."
                if [[ "$STASHED" == "true" ]]; then
                    warn "Restoring stashed changes..."
                    git stash pop || true
                    STASHED=false
                fi
                exit 1
            }
        else
            error "Cannot fast-forward merge. Branch has diverged."
            error "Resolve manually: git merge origin/$BRANCH"
            if [[ "$STASHED" == "true" ]]; then
                warn "Restoring stashed changes..."
                git stash pop || true
                STASHED=false
            fi
            exit 1
        fi
    fi

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
    step "Building new Docker image"

    run docker compose build || {
        error "Docker build failed."
        exit 1
    }

    success "Image built successfully"
}

# ─── Restart container ────────────────────────────────────────────────────────

restart_container() {
    step "Starting container"

    # Container may already be stopped (restic snapshot stops it earlier)
    run docker compose down 2>/dev/null || true

    run docker compose up -d || {
        error "Failed to start container."
        exit 1
    }
    log "Container starting..."
}

# ─── Health check ─────────────────────────────────────────────────────────────

_get_container_ip() {
    # Get the container's internal IP via docker inspect so the health check
    # works even without host port mapping (e.g., behind Caddy reverse proxy).
    local cid
    cid=$(docker compose ps -q web 2>/dev/null)
    if [[ -z "$cid" ]]; then
        echo ""
        return
    fi
    local ip
    ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$cid" 2>/dev/null)
    echo "${ip:-localhost}"
}

_get_allowed_host() {
    # Read first ALLOWED_HOSTS value from .env for the Host header.
    # Django returns 400 if the Host header doesn't match ALLOWED_HOSTS.
    if [[ -f .env ]]; then
        local hosts
        hosts=$(grep -E '^ALLOWED_HOSTS=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | cut -d, -f1)
        if [[ -n "$hosts" ]]; then
            echo "$hosts"
            return
        fi
    fi
    echo "localhost"
}

health_check() {
    step "Health check (timeout: ${HEALTH_TIMEOUT}s)"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would poll container for HTTP 200 on port $APP_PORT"
        return 0
    fi

    local container_ip allowed_host
    container_ip=$(_get_container_ip)
    allowed_host=$(_get_allowed_host)

    local elapsed=0
    while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
        local http_code
        if [[ -n "$container_ip" ]]; then
            http_code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${allowed_host}" "http://${container_ip}:${APP_PORT}/" 2>/dev/null || echo "000")
        else
            http_code="000"
        fi

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

    # Stop current container
    docker compose down 2>/dev/null || true

    # Prefer restic restore if we took a restic snapshot
    if [[ "$RESTIC_AVAILABLE" == "true" && -n "$RESTIC_SNAPSHOT_ID" ]]; then
        _rollback_restic
    else
        _rollback_legacy
    fi
}

_rollback_restic() {
    warn "Restoring restic snapshot ${RESTIC_SNAPSHOT_ID}..."

    # Get the directory that was originally snapshotted
    local app_dir
    app_dir="$(pwd)"

    local restore_output
    restore_output=$(restic restore "$RESTIC_SNAPSHOT_ID" --target / \
        --delete --include "$app_dir" 2>&1) || {
        # Restic may report non-fatal errors (e.g., can't chmod parent dirs)
        if echo "$restore_output" | grep -q "Summary:.*Restored"; then
            warn "Restore completed with non-fatal errors (likely parent directory permissions)."
            log "$restore_output"
        else
            error "Restic restore failed! Attempting legacy rollback..."
            error "$restore_output"
            _rollback_legacy
            return $?
        fi
    }

    success "Files restored from restic snapshot"

    # Start container (entrypoint.sh handles migrate + collectstatic)
    docker compose up -d 2>/dev/null || {
        error "Failed to start container after restic restore."
        return 1
    }

    _verify_rollback
}

_rollback_legacy() {
    if [[ -z "$OLD_SHA" ]]; then
        error "No rollback point saved. Manual intervention required."
        return 1
    fi

    warn "Rolling back to commit ${OLD_SHA:0:12} (legacy method)..."

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

    _verify_rollback
}

_verify_rollback() {
    log "Verifying rollback..."
    local container_ip allowed_host
    container_ip=$(_get_container_ip)
    allowed_host=$(_get_allowed_host)
    local elapsed=0
    while [[ $elapsed -lt 30 ]]; do
        local http_code
        if [[ -n "$container_ip" ]]; then
            http_code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${allowed_host}" "http://${container_ip}:${APP_PORT}/" 2>/dev/null || echo "000")
        else
            http_code="000"
        fi
        if [[ "$http_code" =~ ^(200|301|302)$ ]]; then
            success "Rollback successful — application is running"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    error "Rollback health check also failed. Manual intervention required."
    error "Old commit: ${OLD_SHA:-unknown}"
    error "Restic snapshot: ${RESTIC_SNAPSHOT_ID:-none}"
    error "Django backup: ${BACKUP_PATH:-none}"
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
    if [[ "$SKIP_BACKUP" == "true" ]]; then
        echo -e "  Backup: ${CYAN}skipped${NC}"
    elif [[ "$RESTIC_AVAILABLE" == "true" ]]; then
        echo -e "  Backup: ${CYAN}restic snapshot${NC}"
    else
        echo -e "  Backup: ${CYAN}Django backup${NC}"
    fi
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
    if [[ -n "$RESTIC_SNAPSHOT_ID" ]]; then
        success "Restic snapshot: $RESTIC_SNAPSHOT_ID"
    elif [[ -n "$BACKUP_PATH" ]]; then
        success "Django backup: $BACKUP_PATH"
    fi
    success "Log: $LOG_FILE"
    echo ""

    # Prune old restic snapshots
    if [[ "$RESTIC_AVAILABLE" == "true" ]]; then
        local keep="${RESTIC_KEEP_LAST:-10}"
        log "Pruning restic snapshots (keeping last $keep)..."
        restic forget --keep-last "$keep" --prune --compact 2>/dev/null || {
            warn "Restic prune failed (non-critical). Run manually: ./backup.sh prune"
        }
    fi

    # Offer to prune old Docker images
    local dangling
    dangling=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$dangling" -gt 0 ]]; then
        log "$dangling dangling Docker image(s) found. Clean up with: docker image prune -f"
    fi
}

main "$@"
