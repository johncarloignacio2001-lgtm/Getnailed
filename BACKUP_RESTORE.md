# Backup and Restore (safe guidance)

This project includes a safe management command to create PostgreSQL backups and record lightweight metadata.

## Backup

Requirements:
- PostgreSQL client tools (`pg_dump`) available on the PATH or set `PG_DUMP_PATH` env var.
- If your database requires a password, set `PGPASSWORD` in the environment when running the command (do NOT check secrets into source control).

To create a backup:

```bash
# from repository root
python manage.py backup_db
```

This writes a dump file to `backups/` and creates `backups/last_backup.json` with non-secret metadata about the last backup.

## Restore

This project intentionally does NOT provide an automatic or web-based restore, to avoid accidental destructive restores. To restore manually, use `pg_restore` on a trusted machine, following your organization policies and verifying data integrity and permissions.

Example restore command (manual, operator-run):

```bash
# ensure you understand and have a tested plan before running
pg_restore -h HOST -p PORT -U USER -d DBNAME path/to/backup-file.dump
```

## Notes
- The management command will refuse to run if the configured `DATABASES['default']['ENGINE']` is not PostgreSQL.
- The command writes metadata but never stores passwords or other secrets.
- For automated scheduled backups, run the management command from a secure runner with restricted environment and rotate backups according to retention policy.
