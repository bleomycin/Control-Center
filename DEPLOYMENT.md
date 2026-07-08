# Production Deployment Checklist — Control Center

Single-user, VPN-only Django app served behind a Caddy + Authelia reverse proxy.
Deployment is automated by `upgrade.sh` (backup → pull → build → restart → health
check → auto-rollback). This checklist covers what `upgrade.sh` does **not** do:
one-time production configuration and post-deploy verification.

Status legend: `[x]` verified this cycle · `[ ]` operator action required on the prod host.

---

## 0. Pre-flight (verified locally against prod-shaped Docker)

These were checked on the local Docker instance with `DEBUG=False`. Re-run after any code change.

- [x] **Migrations are complete** — `manage.py makemigrations --check --dry-run` → *No changes detected*.
- [x] **Full unit suite green** — `make test-unit` → **Ran 1861 tests … OK** (0 failures). (see §5).
- [x] **Full e2e suite green** — `make test-e2e` → **Ran 224 tests … OK** (102 s, 0 failures).
- [x] **Adversarial bug-review pass** — 5-agent review of the Phase 5-6 overhaul; 5 real functional defects fixed with regression tests (commit 266ab76).
- [x] **Prompt-injection / attack-surface findings reconstructed (Wave 3, 2026-07-08)** — the
      266ab76 review's deferred security findings are now written up in
      `.claude/docs/assistant-remediation/WAVE-3-SECURITY-FINDINGS.md` (11 findings + PASS list).
      3 fixed this wave (PI-3 client-sanitizer exfil beacon, PI-4 `update_record` PK
      mass-assignment overwrite, PI-8 bulk-link fail-open default). ⚠️ **2 HIGH items remain an
      owner go/no-go before prod:** PI-1 (write confirmation is prompt-only, not code-enforced)
      and PI-2 (spoofable `[AttachedDriveFiles]` tool-gate). Decide: accept for v1 (single
      trusted user + backups) or run a dedicated confirmation-gate phase first. See §4.
- [x] **Bug-check of the bug-review (2026-07-08)** — 3-lens adversarial review of 266ab76 itself; 7 defects fixed with regression tests (2 proven failing pre-fix), including a drawer soft-lock (send button stuck disabled after mid-stream "New chat") and a stray-frame input-bleed race; the previously uncovered drawer teardown flow now has e2e + live two-profile/headed/iPhone-16e verification with real API turns.
- [x] **Credential allowlist enforced** — all 6 credential models (`GoogleDriveSettings`,
      `EmailSettings`, `CalendarFeedSettings`, `BackupSettings`, `AssistantSettings`,
      `SampleDataStatus`) are blocked from the assistant tool registry, and secret-bearing
      fields (`password`, `token`, `secret`, `api_key`, `refresh_token`, `access_token`)
      redact in `serialize_instance`. Verified: registry exposes 52 models, 0 credential leaks.
- [x] **Background worker (qcluster) healthy** — process pool alive; a probe task round-tripped
      through the ORM broker in ~60 ms with `success=True`.
- [x] **SQLite write-contention cleared** — under 24- and 48-way concurrent write storms with the
      prod `transaction_mode=IMMEDIATE` / WAL config on the real 16-thread gunicorn stack:
      **0 `database is locked`, 0 failures, 0 stalls > 5 s** (tail latency peaked ~3–4 s, far under
      the 20 s `busy_timeout` ceiling). Admission constraint serializes exactly one turn per session,
      the rest cleanly refused as busy — 0 `OperationalError`.
- [x] **`manage.py check --deploy`** — the 5 warnings it reports (SSL redirect, HSTS, cookie-secure
      flags, SECRET_KEY strength) are **all gated behind `ENABLE_SSL` and the prod `.env`**, not code
      defects. Setting the prod env below clears every one. See §2.

---

## 1. Production `.env` (on the prod host — NOT committed)

The running container is only as safe as its `.env`. Confirm every line:

- [ ] `DEBUG=false` — settings hard-`raise ValueError` if `SECRET_KEY` is unset while `DEBUG=False`,
      so a missing key fails fast rather than silently using the insecure dev default.
- [ ] `SECRET_KEY=` — a fresh **50+ char random** value, unique to prod. Never the dev default.
      Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- [ ] `ENABLE_SSL=true` — **required in prod.** This single flag turns on `SECURE_SSL_REDIRECT`,
      `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and 1-year HSTS. Without it the app runs plain-HTTP-cookie mode.
      ⚠️ **`.env.example` does not list this key — see §4 action item.**
- [ ] `ALLOWED_HOSTS=<your.domain>` — the real hostname(s), comma-separated. Not `*`.
- [ ] `ANTHROPIC_API_KEY=` — the production key (the assistant is non-functional without it).
- [ ] `DATABASE_PATH=/app/data/db.sqlite3` — points at the persisted volume (`./persist/data`).
- [ ] `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` — activates the prod overlay
      (drops the published :8000 port; joins external `caddy-net`). Verify merged config with
      `docker compose config`.
- [ ] `DJANGO_SUPERUSER_PASSWORD=` — changed from the `admin`/`admin` example default.
- [ ] `EMAIL_BACKEND=` — set to a real SMTP backend if notification emails are expected
      (defaults to console = emails go to the log, not sent).
- [ ] `RESTIC_PASSWORD=` — set if using restic snapshots for upgrade rollback (recommended;
      run `./backup.sh install && ./backup.sh init` once).

## 2. TLS / proxy chain (Caddy + Authelia)

- [ ] TLS terminates at Caddy; `SECURE_PROXY_SSL_HEADER` already trusts `X-Forwarded-Proto` — confirm
      Caddy sets it.
- [ ] Authelia (or equivalent) fronts the app — there is **no Django login middleware**; the app
      assumes the proxy handles authentication. Do **not** expose the container port publicly.
- [ ] After first HTTPS load, confirm a form POST (send one assistant message) does not 403 on CSRF.
      If it does, add `CSRF_TRUSTED_ORIGINS=https://<your.domain>` (currently unset/`[]`).

## 3. Data & rollback safety

- [ ] Pre-upgrade backup runs automatically (`upgrade.sh` takes a restic snapshot, or Django backup
      with `--no-restic`). Confirm at least one good backup exists before the first prod upgrade.
- [ ] `upgrade.sh` tags the current image `controlcenter:pre-upgrade` and **auto-rolls-back on a failed
      health check** (`GET /` non-200). Rollback path tested in the script; know how to invoke it manually.
- [ ] Persisted volumes (`./persist/{data,media,backups}`) are on durable storage and included in
      off-host backups.

## 4. Known gaps / follow-ups (not blockers, but decide before shipping)

- [x] **`.env.example` was missing `ENABLE_SSL`** — fixed this cycle: added a commented
      `#ENABLE_SSL=true` block documenting the secure-cookie/HSTS/SSL-redirect switch.
- [x] **qcluster supervision — RESOLVED (Wave 3, 2026-07-08).** qcluster is now its own
      Compose service (`docker-compose.yml`): same image, `command: python manage.py qcluster`,
      shared `.env` + SQLite volume, `restart: unless-stopped`, `depends_on: web
      (service_healthy)`. A dead worker is now auto-restarted by Docker instead of silently
      orphaning under gunicorn. (Blast radius was broader than first thought — it also carried
      the `setup_schedules` notifications, not just chat titles.) Verified live: the separate
      service processes both scheduled notifications and async title tasks across containers.
- [x] **Error tracking (Sentry/rollbar) — DECIDED: SKIP (Wave 3).** Errors surface in
      gunicorn/qcluster stdout (`--error-logfile -`); a third-party sink would ship
      personal-affairs context off-host for a single-user app. Revisit only if the app gains
      more users or leaves the VPN.
- [ ] **⚠️ Prompt-injection write surface (owner decision — see §0 and
      `WAVE-3-SECURITY-FINDINGS.md`).** Write-tool confirmation is enforced only by the system
      prompt (PI-1), and the `[AttachedDriveFiles]` tool-gate is spoofable from untrusted email
      content (PI-2). For a single trusted user with backups this is a defensible accepted
      risk; if not accepting, run the code-enforced confirmation-gate phase before shipping.

## 5. Commands

```bash
# Pre-flight (run inside the container)
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py check --deploy
make test-unit          # full unit suite (serial, canonical)
make test-e2e           # Playwright e2e (local venv)

# Deploy / rollback
./upgrade.sh --dry-run  # preview
./upgrade.sh            # backup → pull → build → restart → health check → auto-rollback
docker compose config   # verify prod overlay merged correctly

# Post-deploy smoke (through the real domain)
#  1. Load the dashboard over HTTPS (200, no mixed-content).
#  2. Open the assistant, send one message, confirm it streams and persists (CSRF ok).
#  3. Rename/delete a session (confirms write path + IMMEDIATE-mode locking).
#  4. Confirm a new session's title auto-generates within a few seconds (qcluster alive).
```
