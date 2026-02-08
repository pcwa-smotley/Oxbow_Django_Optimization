# django_backend/optimization_api/management/commands/migrate_alerts.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from optimization_api.models import AlertThreshold

'''
HOW TO RUN THIS COMMAND:
# First, make and run database migrations for the new fields
python manage.py makemigrations
python manage.py migrate

# Then run the alert migration command
python manage.py migrate_alerts

Purpose
The command serves two main functions:
1. Migrate Existing Alerts to Categories
When you upgrade to the new alert system, your existing alerts won't have the new fields like category, 
special_type, and metadata. 

It goes through all existing AlertThreshold objects in your database
Assigns appropriate categories based on the parameter type:

r4_flow, r11_flow, r30_flow → category: 'flow'
afterbay_elevation, float_level → category: 'afterbay'
oxph_power, mfra_power → category: 'generation'
Others → category: 'general'


Sets the special_type field (defaulting to 'standard' for existing alerts)

2. Create Default Alert Sets
For users who don't have certain basic alerts configured, it creates a default set:

R4 Low/High Flow alerts (400/500 CFS)
Afterbay Low/High Elevation alerts (1166.5/1176.0 ft)
Float Level Change detection (disabled by default)

How to Use It
After you've added the new fields to your AlertThreshold model and run database migrations:

What It Does Step by Step

Updates existing alerts with appropriate categories
Creates default alerts for users who don't have them
Preserves all existing alert settings (thresholds, notification preferences, etc.)
Reports progress as it migrates each alert

Example Output
Migrating alerts to new categorized system...
Updated alert: R4 Low Flow Alert -> flow
Updated alert: High Afterbay Elevation -> afterbay
Updated alert: OXPH Power Alert -> generation
Successfully migrated 12 alerts
Created default alerts for users

Why It's Needed
Without this migration:

Your existing alerts would appear uncategorized in the new UI
The accordion categories wouldn't show correct counts
Special alert types (rafting, float change) wouldn't work properly
Users might be missing important baseline alerts

This ensures a smooth transition from your current simple alert system to the enhanced categorized version without 
losing any existing configurations or requiring manual re-entry of alerts.
'''


class Command(BaseCommand):
    help = 'Migrate existing alerts to new categorized system'

    def handle(self, *args, **options):
        self.stdout.write('Migrating alerts to new categorized system...')

        # Update existing alerts with categories
        alert_mappings = {
            # Flow alerts
            'r4_flow': 'flow',
            'r11_flow': 'flow',
            'r30_flow': 'flow',

            # Afterbay alerts
            'afterbay_elevation': 'afterbay',
            'float_level': 'afterbay',

            # Generation alerts
            'oxph_power': 'generation',
            'mfra_power': 'generation',

            # Other
            'net_flow': 'general',
            'spillage': 'general'
        }

        updated_count = 0

        for alert in AlertThreshold.objects.all():
            # Set category based on parameter
            if alert.parameter in alert_mappings:
                alert.category = alert_mappings[alert.parameter]

                # Set special types
                if 'High OXPH Power' in alert.name or 'Low OXPH Power' in alert.name:
                    # Convert to deviation alert if it's monitoring OXPH limits
                    alert.special_type = 'standard'  # Keep as standard for now

                alert.save()
                updated_count += 1
                self.stdout.write(f'Updated alert: {alert.name} -> {alert.category}')

        self.stdout.write(
            self.style.SUCCESS(f'Successfully migrated {updated_count} alerts')
        )

        # Create default alerts for users who don't have them
        self._create_default_alerts()

    def _create_default_alerts(self):
        """Create default alert set for existing users"""

        default_alerts = [
            # Flow alerts
            {
                'name': 'R4 Low Flow Alert',
                'parameter': 'r4_flow',
                'condition': 'less_than',
                'threshold_value': 400,
                'category': 'flow',
                'severity': 'warning'
            },
            {
                'name': 'R4 High Flow Alert',
                'parameter': 'r4_flow',
                'condition': 'greater_than',
                'threshold_value': 500,
                'category': 'flow',
                'severity': 'warning'
            },

            # Afterbay alerts
            {
                'name': 'Low Afterbay Elevation',
                'parameter': 'afterbay_elevation',
                'condition': 'less_than',
                'threshold_value': 1166.5,
                'category': 'afterbay',
                'severity': 'critical'
            },
            {
                'name': 'High Afterbay Elevation',
                'parameter': 'afterbay_elevation',
                'condition': 'greater_than',
                'threshold_value': 1176.0,
                'category': 'afterbay',
                'severity': 'warning'
            },

            # Float change alert
            {
                'name': 'Float Level Change',
                'parameter': 'float_level',
                'condition': 'change_detected',
                'threshold_value': 0.1,
                'category': 'afterbay',
                'severity': 'info',
                'special_type': 'float_change',
                'is_active': False  # Disabled by default
            }
        ]

        # Create alerts for users who don't have them
        for user in User.objects.filter(is_active=True):
            for alert_config in default_alerts:
                AlertThreshold.objects.get_or_create(
                    user=user,
                    name=alert_config['name'],
                    defaults=alert_config
                )

        self.stdout.write('Created default alerts for users')