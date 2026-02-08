# django_backend/optimization_api/management/commands/run_alerts.py

import time
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from optimization_api.alerting import alerting_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the alerting system to check for threshold violations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Check interval in seconds (default: 60)'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once and exit (don\'t loop)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging'
        )

    def handle(self, *args, **options):
        if options['verbose']:
            logging.basicConfig(level=logging.DEBUG)

        interval = options['interval']
        run_once = options['once']

        self.stdout.write(
            self.style.SUCCESS(f'Starting ABAY alerting service (interval: {interval}s)')
        )

        try:
            if run_once:
                self._check_alerts_once()
            else:
                self._run_alert_loop(interval)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('Alerting service stopped by user')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Alerting service error: {str(e)}')
            )
            raise

    def _check_alerts_once(self):
        """Run alert checking once"""
        self.stdout.write('Checking alerts...')

        # Get current system data (in production, this would come from your PI system)
        system_data = self._get_current_system_data()

        # Check all alerts
        triggered_alerts = alerting_service.check_all_alerts(system_data)

        if triggered_alerts:
            self.stdout.write(
                self.style.WARNING(f'Triggered {len(triggered_alerts)} alerts')
            )
            for alert in triggered_alerts:
                self.stdout.write(f'  - {alert["alert_name"]} for {alert["username"]}')
        else:
            self.stdout.write(
                self.style.SUCCESS('No alerts triggered')
            )

    def _run_alert_loop(self, interval):
        """Run continuous alert checking loop"""
        self.stdout.write(f'Running continuous alert checking every {interval} seconds...')
        self.stdout.write('Press Ctrl+C to stop')

        while True:
            try:
                start_time = time.time()

                # Get current system data
                system_data = self._get_current_system_data()

                # Check all alerts
                triggered_alerts = alerting_service.check_all_alerts(system_data)

                # Log results
                if triggered_alerts:
                    self.stdout.write(
                        f'[{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}] '
                        f'Triggered {len(triggered_alerts)} alerts'
                    )
                else:
                    # Only show "no alerts" message in verbose mode
                    if hasattr(self, 'verbose') and self.verbose:
                        self.stdout.write(
                            f'[{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}] '
                            'No alerts triggered'
                        )

                # Sleep for the remaining interval time
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)

                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error in alert loop: {str(e)}')
                )
                # Sleep a bit before retrying
                time.sleep(10)

    def _get_current_system_data(self):
        """
        Get current system data for alert checking
        In production, this would connect to your PI system or database
        """
        # For demonstration, return simulated data with some variation
        now = datetime.now()

        return {
            'afterbay_elevation': 1170.5 + (now.minute % 10) * 0.1 - 0.5,  # Simulate variation
            'oxph_power': 2.8 + (now.second % 30) * 0.1,
            'r4_flow': 850 + (now.minute % 20) * 10,
            'r30_flow': 1250 + (now.minute % 15) * 20,
            'mfra_power': 165 + (now.second % 40) * 2,
            'float_level': 1173.0,
            'net_flow': 50 + (now.minute % 25) * 5,
            'spillage': max(0, (now.minute % 60) - 55) * 2,  # Occasional spillage
            'timestamp': now.isoformat()
        }


# django_backend/optimization_api/management/commands/create_test_alerts.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from optimization_api.models import AlertThreshold


class Command(BaseCommand):
    help = 'Create test alert thresholds for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='admin',
            help='Username to create alerts for (default: admin)'
        )

    def handle(self, *args, **options):
        username = options['username']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User "{username}" does not exist')
            )
            return

        # Create sample alert thresholds
        alerts_to_create = [
            {
                'name': 'High Afterbay Elevation',
                'description': 'Alert when afterbay elevation exceeds 1172 ft',
                'parameter': 'afterbay_elevation',
                'condition': 'greater_than',
                'threshold_value': 1172.0,
                'severity': 'warning'
            },
            {
                'name': 'Low Afterbay Elevation',
                'description': 'Alert when afterbay elevation drops below 1169 ft',
                'parameter': 'afterbay_elevation',
                'condition': 'less_than',
                'threshold_value': 1169.0,
                'severity': 'critical'
            },
            {
                'name': 'High OXPH Power',
                'description': 'Alert when OXPH power exceeds 5.5 MW',
                'parameter': 'oxph_power',
                'condition': 'greater_than',
                'threshold_value': 5.5,
                'severity': 'info'
            },
            {
                'name': 'Low R4 Flow',
                'description': 'Alert when R4 flow drops below 800 CFS',
                'parameter': 'r4_flow',
                'condition': 'less_than',
                'threshold_value': 800.0,
                'severity': 'warning'
            },
            {
                'name': 'Spillage Detected',
                'description': 'Alert when spillage is detected',
                'parameter': 'spillage',
                'condition': 'greater_than',
                'threshold_value': 0.0,
                'severity': 'critical'
            }
        ]

        created_count = 0
        for alert_data in alerts_to_create:
            alert, created = AlertThreshold.objects.get_or_create(
                user=user,
                name=alert_data['name'],
                defaults=alert_data
            )

            if created:
                created_count += 1
                self.stdout.write(f'Created alert: {alert.name}')
            else:
                self.stdout.write(f'Alert already exists: {alert.name}')

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} new alerts for user "{username}"')
        )


# django_backend/optimization_api/management/commands/test_websockets.py

import asyncio
import json
from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer


class Command(BaseCommand):
    help = 'Test WebSocket functionality by sending a test message'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            required=True,
            help='User ID to send test message to'
        )
        parser.add_argument(
            '--message',
            type=str,
            default='Test message from management command',
            help='Message to send'
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        message = options['message']

        self.stdout.write(f'Sending test WebSocket message to user {user_id}...')

        # Get the channel layer
        channel_layer = get_channel_layer()

        if not channel_layer:
            self.stdout.write(
                self.style.ERROR('Channel layer not configured')
            )
            return

        # Create test alert data
        test_alert = {
            'type': 'alert_notification',
            'alert': {
                'id': 999,
                'name': 'Test Alert',
                'severity': 'info',
                'parameter': 'test_parameter',
                'triggered_value': 123.45,
                'threshold_value': 100.0,
                'message': message,
                'timestamp': '2025-01-01T12:00:00Z'
            }
        }

        # Send the message
        asyncio.run(self._send_message(channel_layer, user_id, test_alert))

        self.stdout.write(
            self.style.SUCCESS(f'Test message sent to user {user_id}')
        )

    async def _send_message(self, channel_layer, user_id, data):
        """Send message via channel layer"""
        user_channel = f"user_{user_id}"

        await channel_layer.group_send(
            user_channel,
            {
                'type': 'send_alert',
                'data': data
            }
        )


# django_backend/optimization_api/management/commands/monitor_system.py

import time
import json
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from optimization_api.alerting import alerting_service


class Command(BaseCommand):
    help = 'Monitor system and display real-time data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Monitoring interval in seconds (default: 10)'
        )

    def handle(self, *args, **options):
        interval = options['interval']

        self.stdout.write(
            self.style.SUCCESS(f'Starting ABAY system monitor (interval: {interval}s)')
        )
        self.stdout.write('Press Ctrl+C to stop\n')

        try:
            while True:
                # Clear screen (works on most terminals)
                print('\033[2J\033[H')

                # Get current system data
                system_data = self._get_current_system_data()

                # Display header
                self.stdout.write('=' * 60)
                self.stdout.write(f'ABAY System Monitor - {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
                self.stdout.write('=' * 60)

                # Display system data
                for key, value in system_data.items():
                    if key != 'timestamp':
                        if isinstance(value, float):
                            display_value = f"{value:.2f}"
                        else:
                            display_value = str(value)

                        self.stdout.write(f'{key:.<25} {display_value}')

                self.stdout.write('\n' + '=' * 60)

                # Check for alerts
                triggered_alerts = alerting_service.check_all_alerts(system_data)

                if triggered_alerts:
                    self.stdout.write(
                        self.style.ERROR(f'🚨 {len(triggered_alerts)} ALERTS TRIGGERED:')
                    )
                    for alert in triggered_alerts:
                        self.stdout.write(
                            f'  • {alert["alert_name"]} ({alert["severity"].upper()}) - {alert["username"]}'
                        )
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ No alerts triggered')
                    )

                # Wait for next update
                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\nSystem monitor stopped by user')
            )

    def _get_current_system_data(self):
        """Get simulated system data"""
        now = datetime.now()

        return {
            'afterbay_elevation': 1170.5 + (now.minute % 10) * 0.1 - 0.5,
            'oxph_power': 2.8 + (now.second % 30) * 0.1,
            'r4_flow': 850 + (now.minute % 20) * 10,
            'r30_flow': 1250 + (now.minute % 15) * 20,
            'mfra_power': 165 + (now.second % 40) * 2,
            'float_level': 1173.0,
            'net_flow': 50 + (now.minute % 25) * 5,
            'spillage': max(0, (now.minute % 60) - 55) * 2,
        }