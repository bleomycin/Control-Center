"""Restore database and media files from a backup archive."""
import shutil
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Restore database and media from a backup archive'

    def add_arguments(self, parser):
        parser.add_argument(
            'archive', type=str,
            help='Path to the .tar.gz backup archive',
        )

    def handle(self, *args, **options):
        archive_path = Path(options['archive'])

        if not archive_path.exists():
            raise CommandError(f'Archive not found: {archive_path}')
        if not tarfile.is_tarfile(str(archive_path)):
            raise CommandError(f'Not a valid tar archive: {archive_path}')

        # Validate archive contents
        with tarfile.open(archive_path, 'r:gz') as tar:
            members = tar.getnames()
            if 'db.sqlite3' not in members:
                raise CommandError('Archive missing db.sqlite3')
            if not any(m.startswith('media') for m in members):
                raise CommandError('Archive missing media/ directory')

        db_path = Path(settings.DATABASES['default']['NAME'])
        media_root = Path(settings.MEDIA_ROOT)

        self.stdout.write(f'Restoring from: {archive_path}')

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Extract archive
            with tarfile.open(archive_path, 'r:gz') as tar:
                tar.extractall(path=tmp_path)

            # Replace database
            src_db = tmp_path / 'db.sqlite3'
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_db), str(db_path))
            self.stdout.write(f'  Database restored ({db_path.stat().st_size:,} bytes)')

            # Replace media directory
            src_media = tmp_path / 'media'
            if src_media.exists():
                if media_root.exists():
                    shutil.rmtree(media_root)
                shutil.copytree(str(src_media), str(media_root))
                file_count = sum(1 for _ in media_root.rglob('*') if _.is_file())
                self.stdout.write(f'  Media restored ({file_count} files)')

        # Run migrations to handle any schema differences
        self.stdout.write('  Running migrations...')
        call_command('migrate', verbosity=0)

        self.stdout.write(self.style.SUCCESS('\nRestore complete.'))
