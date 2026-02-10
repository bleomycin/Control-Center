"""Django-Q2 callable wrapper for automated backups."""
from dashboard.management.commands.backup import create_backup, get_backup_dir, prune_backups


def run_backup():
    """Run a backup and prune old archives (keep last 7 days)."""
    backup_dir = get_backup_dir()
    create_backup(backup_dir=backup_dir)
    deleted = prune_backups(backup_dir, keep=7)
    for old in deleted:
        old.unlink()
