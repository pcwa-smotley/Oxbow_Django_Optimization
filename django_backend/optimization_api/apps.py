# django_backend/optimization_api/apps.py

from django.apps import AppConfig


class OptimizationApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'optimization_api'

    def ready(self):
        """Called when Django starts - set up any initialization here"""
        # Set up SQLite optimizations
        from django.db.backends.signals import connection_created
        
        def optimize_sqlite(sender, connection, **kwargs):
            """Apply SQLite optimizations for better concurrency"""
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                # Write-Ahead Logging - much better for concurrent access
                cursor.execute('PRAGMA journal_mode = WAL;')
                # Faster writes, still safe
                cursor.execute('PRAGMA synchronous = NORMAL;')
                # 64MB cache for better performance
                cursor.execute('PRAGMA cache_size = -64000;')
                # Use memory for temporary tables
                cursor.execute('PRAGMA temp_store = MEMORY;')
                # 256MB memory-mapped I/O
                cursor.execute('PRAGMA mmap_size = 268435456;')
        
        connection_created.connect(optimize_sqlite)