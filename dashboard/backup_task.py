"""Django-Q2 callable wrapper for automated backups."""
from dashboard.management.commands.backup import create_backup, get_backup_dir, prune_backups


def run_backup():
    """Run a backup and prune old archives based on BackupSettings retention."""
    from dashboard.models import BackupSettings

    config = BackupSettings.load()
    backup_dir = get_backup_dir()
    create_backup(backup_dir=backup_dir)
    deleted = prune_backups(backup_dir, keep=config.retention_count)
    for old in deleted:
        old.unlink()
