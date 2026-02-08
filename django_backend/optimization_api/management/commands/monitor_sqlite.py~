# django_backend/optimization_api/management/commands/monitor_sqlite.py


'''
Ways to use this file:
1) > python manage.py monitor_sqlite
2) Setting Up Automated Monitoring
    You could also add a cron job to run it weekly:
    # Add to crontab (crontab -e)
    # Run every Monday at 9 AM
    0 9 * * 1 cd /path/to/django_backend && python manage.py monitor_sqlite
3)
'''

from django.core.management.base import BaseCommand
from django.conf import settings
import re
from pathlib import Path


class Command(BaseCommand):
    help = 'Monitor SQLite database lock events'

    def handle(self, *args, **options):
        log_file = Path(settings.BASE_DIR) / 'logs' / 'sqlite_locks.log'

        if not log_file.exists():
            self.stdout.write(self.style.WARNING('No SQLite log file found yet.'))
            return

        lock_count = 0
        lock_pattern = re.compile(r'database is locked|SQLITE_BUSY|OperationalError')

        self.stdout.write(f"\nAnalyzing SQLite logs from: {log_file}")
        self.stdout.write("-" * 60)

        with open(log_file, 'r') as f:
            for line in f:
                if lock_pattern.search(line):
                    lock_count += 1
                    self.stdout.write(self.style.ERROR(f"Lock event: {line.strip()}"))

        self.stdout.write("-" * 60)
        self.stdout.write(f"Total lock events found: {lock_count}")

        if lock_count > 10:
            self.stdout.write(self.style.ERROR("\n⚠️  WARNING: High number of lock events detected!"))
            self.stdout.write(self.style.ERROR("Consider migrating to PostgreSQL if this continues."))
        elif lock_count > 0:
            self.stdout.write(self.style.SUCCESS("\n✓ Some lock events found, but within acceptable range."))
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ No lock events found - SQLite is handling your load well!"))