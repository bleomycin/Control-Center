"""Create a safe, consistent backup of the database and media files."""
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def get_backup_dir():
    return Path(os.environ.get('BACKUP_DIR', settings.BASE_DIR / 'backups'))


def create_backup(backup_dir=None, stdout=None):
    """Core backup logic — callable from management command and django-q2.

    Returns the path to the created archive.
    """
    backup_dir = backup_dir or get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    archive_name = f'controlcenter-backup-{timestamp}.tar.gz'
    archive_path = backup_dir / archive_name

    db_path = settings.DATABASES['default']['NAME']
    media_root = Path(settings.MEDIA_ROOT)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Safe SQLite backup (handles WAL mode, consistent snapshot)
        dst_db = tmp_path / 'db.sqlite3'
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(dst_db))
        src.backup(dst)
        src.close()
        dst.close()

        if stdout:
            stdout.write(f'  Database backed up ({dst_db.stat().st_size:,} bytes)')

        # Copy media directory
        dst_media = tmp_path / 'media'
        if media_root.exists() and any(media_root.iterdir()):
            shutil.copytree(media_root, dst_media)
            if stdout:
                file_count = sum(1 for _ in dst_media.rglob('*') if _.is_file())
                stdout.write(f'  Media backed up ({file_count} files)')
        else:
            dst_media.mkdir()
            if stdout:
                stdout.write('  Media directory empty, creating placeholder')

        # Package into tar.gz
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(str(dst_db), arcname='db.sqlite3')
            tar.add(str(dst_media), arcname='media')

    return archive_path


def prune_backups(backup_dir, keep):
    """Delete oldest backups, keeping only the most recent `keep` archives."""
    archives = sorted(
        backup_dir.glob('controlcenter-backup-*.tar.gz'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    to_delete = archives[keep:]
    return to_delete


class Command(BaseCommand):
    help = 'Create a backup of the database and media files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=0,
            help='Keep only N most recent backups (0 = keep all)',
        )
        parser.add_argument(
            '--dir', type=str, default=None,
            help='Override backup directory',
        )

    def handle(self, *args, **options):
        backup_dir = Path(options['dir']) if options['dir'] else get_backup_dir()

        self.stdout.write('Creating backup...')
        archive_path = create_backup(backup_dir=backup_dir, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            f'\nBackup created: {archive_path} ({archive_path.stat().st_size:,} bytes)'
        ))

        keep = options['keep']
        if keep > 0:
            deleted = prune_backups(backup_dir, keep)
            for old in deleted:
                old.unlink()
                self.stdout.write(f'  Pruned: {old.name}')
            if deleted:
                self.stdout.write(self.style.SUCCESS(
                    f'  Kept {keep} backup(s), pruned {len(deleted)}'
                ))
