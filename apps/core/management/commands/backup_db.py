import os
import json
import subprocess
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Create a PostgreSQL dump backup and write lightweight metadata. Does not perform restores.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=str(Path(settings.BASE_DIR) / 'backups'))
        parser.add_argument('--pg-dump-path', default=os.getenv('PG_DUMP_PATH', 'pg_dump'))

    def handle(self, *args, **options):
        out_dir = Path(options['output_dir'])
        out_dir.mkdir(parents=True, exist_ok=True)

        db = settings.DATABASES.get('default', {})
        engine = db.get('ENGINE', '')
        if 'postgresql' not in engine:
            raise CommandError('backup_db only supports PostgreSQL in this project.')

        name = db.get('NAME')
        host = db.get('HOST') or 'localhost'
        port = db.get('PORT') or '5432'
        user = db.get('USER')

        timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        filename = f"backup-{name}-{timestamp}.sql.gz"
        out_path = out_dir / filename

        pg_dump = options['pg_dump_path']

        # Build command without embedding password on the command-line
        cmd = [pg_dump, '-h', host, '-p', str(port), '-U', user, '-F', 'c', name]

        env = os.environ.copy()
        # It's advised that the operator sets PGPASSWORD in the environment when running.
        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as proc:
                # Pipe through gzip
                with out_path.open('wb') as fh:
                    proc_stdout, proc_stderr = proc.communicate()
                    if proc.returncode not in (0, None):
                        raise CommandError(f'pg_dump failed: {proc_stderr.decode("utf8", errors="replace")}')
                    fh.write(proc_stdout)
        except FileNotFoundError:
            raise CommandError(f'pg_dump not found at {pg_dump}. Ensure PostgreSQL client tools are installed and PG_DUMP_PATH is set.')

        # Write metadata (no secrets)
        metadata = {
            'timestamp': timestamp,
            'filename': filename,
            'db_name': name,
            'host': host,
            'port': port,
            'size_bytes': out_path.stat().st_size,
        }
        meta_file = out_dir / 'last_backup.json'
        with meta_file.open('w') as fh:
            json.dump(metadata, fh)

        self.stdout.write(self.style.SUCCESS(f'Backup written to {out_path}'))
*** End Patch