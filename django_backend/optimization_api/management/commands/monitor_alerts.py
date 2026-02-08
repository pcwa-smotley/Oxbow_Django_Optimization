# django_backend/optimization_api/management/commands/monitor_alerts.py

import time
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monitor PI data and run alerting system'

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
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Run in test mode with simulated data'
        )
        parser.add_argument(
            '--test-twilio',
            action='store_true',
            help='Test Twilio configuration before starting'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Only check alerts for specific username'
        )

    def handle(self, *args, **options):
        # Import here to avoid circular imports
        from optimization_api.alerting import alerting_service
        from optimization_api.models import SystemStatus

        if options['verbose']:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)

        interval = options['interval']
        run_once = options['once']
        test_mode = options['test_mode']
        specific_user = options['user']

        # Test Twilio if requested
        if options['test_twilio']:
            self._test_twilio_configuration()
            if run_once:
                return

        if test_mode:
            self.stdout.write(
                self.style.WARNING('Running in TEST MODE - using simulated data')
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting ABAY Alert Monitoring Service\n'
                f'Check interval: {interval} seconds\n'
                f'Mode: {"Test" if test_mode else "Production"}\n'
                f'User filter: {specific_user or "All users"}'
            )
        )

        try:
            if run_once:
                self._run_monitoring_cycle(alerting_service, SystemStatus, test_mode=test_mode,
                                           user_filter=specific_user)
            else:
                self._run_continuous_monitoring(alerting_service, SystemStatus, interval, test_mode=test_mode,
                                                user_filter=specific_user)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\nMonitoring service stopped by user')
            )
            self._update_system_status(SystemStatus, 'offline', 'Service stopped by user')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Monitoring service error: {str(e)}')
            )
            self._update_system_status(SystemStatus, 'offline', f'Service error: {str(e)}')
            raise

    def _run_monitoring_cycle(self, alerting_service, SystemStatus, test_mode=False, user_filter=None):
        """Run a single monitoring cycle"""
        self.stdout.write('🔄 Running monitoring cycle...')

        try:
            # Get system data
            if test_mode:
                system_data = self._get_test_data()
            else:
                system_data = alerting_service.fetch_current_pi_data()

            if not system_data:
                self.stdout.write(
                    self.style.ERROR('❌ No system data available')
                )
                self._update_system_status(SystemStatus, 'degraded', 'No PI data available')
                return

            # Display current values
            self.stdout.write(
                self.style.SUCCESS(f'📊 Current System State:')
            )
            for param, value in system_data.items():
                if param != 'timestamp' and isinstance(value, (int, float)):
                    self.stdout.write(f'   {param}: {value:.2f}')

            # Check alerts
            if user_filter:
                from django.contrib.auth.models import User
                try:
                    user = User.objects.get(username=user_filter)
                    triggered_alerts = alerting_service.check_user_alerts(user.id, system_data)
                except User.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'User "{user_filter}" not found')
                    )
                    return
            else:
                triggered_alerts = alerting_service.check_all_alerts(system_data)

            # Display results
            if triggered_alerts:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n🚨 {len(triggered_alerts)} ALERTS TRIGGERED:'
                    )
                )
                for alert in triggered_alerts:
                    self.stdout.write(
                        f"   • {alert['alert_name']} ({alert['severity'].upper()}) "
                        f"- User: {alert['username']}"
                    )

                    # Show notification results
                    notifications = alert.get('notifications', {})
                    sent_types = [k for k, v in notifications.items() if v.get('success')]
                    if sent_types:
                        self.stdout.write(f"     ✅ Sent: {', '.join(sent_types)}")

                    failed_types = [k for k, v in notifications.items() if not v.get('success')]
                    if failed_types:
                        self.stdout.write(f"     ❌ Failed: {', '.join(failed_types)}")
            else:
                self.stdout.write(
                    self.style.SUCCESS('✅ No alerts triggered')
                )

            # Update system status
            self._update_system_status(SystemStatus, 'online', 'Monitoring active',
                                       triggered_count=len(triggered_alerts))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error in monitoring cycle: {str(e)}')
            )
            self._update_system_status(SystemStatus, 'degraded', f'Monitoring error: {str(e)}')
            raise

    def _run_continuous_monitoring(self, alerting_service, SystemStatus, interval, test_mode=False, user_filter=None):
        """Run continuous monitoring loop"""
        self.stdout.write(f'🔁 Starting continuous monitoring (Ctrl+C to stop)\n')

        consecutive_failures = 0
        max_failures = 5
        cycle_count = 0

        while True:
            try:
                start_time = time.time()
                cycle_count += 1

                # Run monitoring cycle
                self.stdout.write(f'\n--- Cycle #{cycle_count} ---')
                self._run_monitoring_cycle(alerting_service, SystemStatus, test_mode=test_mode, user_filter=user_filter)

                # Reset failure counter on success
                consecutive_failures = 0

                # Calculate sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)

                if sleep_time > 0:
                    self.stdout.write(
                        f'\n💤 Sleeping for {sleep_time:.1f} seconds...'
                    )
                    time.sleep(sleep_time)

            except Exception as e:
                consecutive_failures += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error in monitoring loop ({consecutive_failures}/{max_failures}): {str(e)}'
                    )
                )

                if consecutive_failures >= max_failures:
                    self.stdout.write(
                        self.style.ERROR('Too many consecutive failures. Stopping service.')
                    )
                    self._update_system_status(SystemStatus, 'offline', f'Too many failures')
                    break

                # Sleep before retrying
                time.sleep(min(60, interval))

    def _get_test_data(self):
        """Generate test data for simulation mode"""
        now = datetime.now()

        return {
            'afterbay_elevation': 1170.5 + (now.minute % 10) * 0.1,
            'oxph_power': 2.8 + (now.second % 30) * 0.1,
            'r4_flow': 850 + (now.minute % 20) * 10,
            'r30_flow': 1250 + (now.minute % 15) * 20,
            'r20_flow': 950 + (now.minute % 8) * 15,
            'r5l_flow': 150 + (now.minute % 6) * 10,
            'mfra_power': 165 + (now.second % 40) * 2,
            'float_level': 1173.0,
            'net_flow': 800 + (now.minute % 8) * 15 - 150 - (now.minute % 6) * 10,
            'spillage': max(0, (now.minute % 60) - 55) * 2,
            'timestamp': now.isoformat()
        }

    def _test_twilio_configuration(self):
        """Test Twilio configuration"""
        self.stdout.write('\n📱 Testing Twilio Configuration...\n')

        if not hasattr(settings, 'TWILIO_ACCOUNT_SID'):
            self.stdout.write(
                self.style.ERROR('❌ TWILIO_ACCOUNT_SID not configured in settings')
            )
            return

        if not hasattr(settings, 'TWILIO_AUTH_TOKEN'):
            self.stdout.write(
                self.style.ERROR('❌ TWILIO_AUTH_TOKEN not configured in settings')
            )
            return

        if not hasattr(settings, 'TWILIO_PHONE_NUMBER'):
            self.stdout.write(
                self.style.ERROR('❌ TWILIO_PHONE_NUMBER not configured in settings')
            )
            return

        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

            # Test account fetch
            account = client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Twilio account active: {account.friendly_name}')
            )

            # Check phone number
            self.stdout.write(
                self.style.SUCCESS(f'✅ Twilio phone number: {settings.TWILIO_PHONE_NUMBER}')
            )

        except ImportError:
            self.stdout.write(
                self.style.WARNING('⚠️  Twilio library not installed - install with: pip install twilio')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Twilio configuration error: {str(e)}')
            )

    def _update_system_status(self, SystemStatus, status, message, triggered_count=0):
        """Update system status in database"""
        try:
            # Only update if we have the alerts_triggered_count field
            status_data = {
                'status': status,
                'pi_data_available': (status in ['online', 'degraded']),
                'alert_system_active': (status == 'online'),
                'status_message': message,
                'last_pi_update': timezone.now() if status in ['online', 'degraded'] else None
            }

            # Check if model has alerts_triggered_count field
            if hasattr(SystemStatus, 'alerts_triggered_count'):
                status_data['alerts_triggered_count'] = triggered_count

            SystemStatus.objects.create(**status_data)
        except Exception as e:
            logger.error(f"Failed to update system status: {str(e)}")