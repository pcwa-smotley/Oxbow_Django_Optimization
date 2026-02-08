# django_backend/optimization_api/alerting.py

import logging
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# Add parent directory to path for abay_opt imports
current_dir = Path(__file__).resolve().parent  # optimization_api/
django_backend_dir = current_dir.parent  # django_backend/
project_root = django_backend_dir.parent  # Oxbow_Django_Optimization/

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from .models import AlertThreshold, AlertLog, UserProfile

# Now import from abay_opt
from abay_opt import data_fetcher

logger = logging.getLogger(__name__)


class AlertingService:
    """Unified service for checking and triggering alerts via multiple channels"""

    def __init__(self):
        self.channel_layer = get_channel_layer()

        # Initialize Twilio client
        self.twilio_client = None
        if hasattr(settings, 'TWILIO_ACCOUNT_SID') and hasattr(settings, 'TWILIO_AUTH_TOKEN'):
            try:
                self.twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
        else:
            logger.warning("Twilio credentials not configured - SMS/voice alerts disabled")


    def check_user_alerts(self, user_id: int, system_data: Dict) -> List[Dict]:
        """Check alerts for a specific user only"""
        try:
            user_alerts = AlertThreshold.objects.filter(
                user_id=user_id,
                is_active=True
            )

            triggered_alerts = []

            for alert in user_alerts:
                parameter_value = system_data.get(alert.parameter)

                if parameter_value is not None:
                    if alert.check_condition(parameter_value) and not alert.is_in_cooldown():
                        triggered_alert = self._trigger_alert(alert, parameter_value, system_data)
                        if triggered_alert:
                            triggered_alerts.append(triggered_alert)

            return triggered_alerts

        except Exception as e:
            logger.error(f"Error checking alerts for user {user_id}: {str(e)}")
            return []

    def _trigger_alert(self, alert: AlertThreshold, triggered_value: float, system_data: Dict) -> Optional[Dict]:
        """
        Trigger an individual alert and send notifications
        """
        try:
            # Create alert message
            message = self._create_alert_message(alert, triggered_value, system_data)

            # Log the alert
            alert_log = AlertLog.objects.create(
                user=alert.user,
                alert_threshold=alert,
                triggered_value=triggered_value,
                message=message,
                severity=alert.severity
            )

            # Update last triggered time
            alert.last_triggered = timezone.now()
            alert.save()

            # Send notifications based on user preferences
            notification_results = self._send_notifications(alert, alert_log, system_data)

            # Update log with notification results
            alert_log.email_sent = notification_results.get('email', {}).get('success', False)
            alert_log.sms_sent = notification_results.get('sms', {}).get('success', False)
            alert_log.voice_sent = notification_results.get('voice', {}).get('success', False)
            alert_log.browser_shown = notification_results.get('browser', {}).get('success', False)
            alert_log.save()

            logger.info(f"Alert triggered: '{alert.name}' for user {alert.user.username}")

            return {
                'alert_id': alert.id,
                'alert_name': alert.name,
                'user_id': alert.user.id,
                'username': alert.user.username,
                'parameter': alert.parameter,
                'triggered_value': triggered_value,
                'threshold_value': alert.threshold_value,
                'condition': alert.condition,
                'severity': alert.severity,
                'message': message,
                'timestamp': alert_log.created_at.isoformat(),
                'notifications': notification_results
            }

        except Exception as e:
            logger.error(f"Error triggering alert '{alert.name}': {str(e)}")
            return None

    def _send_notifications(self, alert: AlertThreshold, alert_log: AlertLog, system_data: Dict) -> Dict:
        """
        Send notifications through all configured channels
        """
        user_profile = alert.user.optimization_profile
        results = {}

        # Email notification
        if alert.email_notification and user_profile.email_notifications and alert.user.email:
            results['email'] = self._send_email_notification(alert, alert_log, system_data)

        # SMS notification
        if alert.sms_notification and user_profile.sms_notifications and user_profile.phone_number:
            results['sms'] = self._send_sms_notification(alert, alert_log, user_profile.phone_number)

        # Voice call for critical alerts
        if alert.voice_notification and alert.severity == 'critical' and user_profile.phone_number:
            results['voice'] = self._send_voice_notification(alert, alert_log, user_profile.phone_number)

        # Browser notification via WebSocket
        if alert.browser_notification and user_profile.browser_notifications:
            results['browser'] = self._send_browser_notification(alert, alert_log)

        return results

    def _create_alert_message(self, alert: AlertThreshold, triggered_value: float, system_data: Dict) -> str:
        """Create a human-readable alert message"""
        parameter_names = {
            'afterbay_elevation': 'Afterbay Elevation',
            'oxph_power': 'OXPH Power',
            'r4_flow': 'R4 Flow',
            'r30_flow': 'R30 Flow',
            'mfra_power': 'MFRA Power',
            'float_level': 'Float Level',
            'net_flow': 'Net Flow',
            'spillage': 'Spillage'
        }

        units = {
            'afterbay_elevation': 'ft',
            'oxph_power': 'MW',
            'r4_flow': 'CFS',
            'r30_flow': 'CFS',
            'mfra_power': 'MW',
            'float_level': 'ft',
            'net_flow': 'CFS',
            'spillage': 'AF'
        }

        param_display = parameter_names.get(alert.parameter, alert.parameter)
        unit = units.get(alert.parameter, '')

        condition_text = {
            'greater_than': f'exceeded {alert.threshold_value}',
            'less_than': f'dropped below {alert.threshold_value}',
            'equal_than': f'equals {alert.threshold_value}',
            'between': f'is between {alert.threshold_value} and {alert.threshold_value_max}',
            'outside_range': f'is outside range {alert.threshold_value} to {alert.threshold_value_max}'
        }

        condition_desc = condition_text.get(alert.condition, f'triggered condition {alert.condition}')

        message = (f"ABAY ALERT: {param_display} {condition_desc} {unit}. "
                   f"Current: {triggered_value:.2f} {unit}. "
                   f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} PT")

        if alert.description:
            message += f" | {alert.description}"

        return message

    def _send_email_notification(self, alert: AlertThreshold, alert_log: AlertLog, system_data: Dict) -> Dict:
        """Send email notification"""
        try:
            subject = f"ABAY Alert: {alert.name} - {alert.severity.upper()}"

            body = f"""
                    ABAY Reservoir Optimization Alert
                    
                    Alert: {alert.name}
                    Severity: {alert.severity.upper()}
                    Parameter: {alert.parameter}
                    Triggered Value: {alert_log.triggered_value:.2f}
                    Threshold: {alert.threshold_value}
                    Condition: {alert.condition}
                    Time: {alert_log.created_at.strftime('%Y-%m-%d %H:%M:%S')} PT
                    
                    Message: {alert_log.message}
                    
                    Current System Status:
                    """
            # Add current system values
            for param, value in system_data.items():
                if param != 'timestamp' and isinstance(value, (int, float)):
                    body += f"- {param}: {value:.2f}\n"

            body += f"""

                    Dashboard: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}
                    
                    To manage your alerts: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/alerts
                    """

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[alert.user.email],
                fail_silently=False
            )

            logger.info(f"Email sent to {alert.user.email} for alert '{alert.name}'")
            return {'success': True, 'to': alert.user.email}

        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _send_sms_notification(self, alert: AlertThreshold, alert_log: AlertLog, phone_number: str) -> Dict:
        """Send SMS notification via Twilio"""
        try:
            if not self.twilio_client:
                return {'success': False, 'error': 'Twilio not configured'}

            # Create concise SMS message (160 char limit)
            message_text = f"ABAY {alert.severity.upper()}: {alert.name}\n{alert_log.message[:100]}"

            message = self.twilio_client.messages.create(
                body=message_text,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )

            logger.info(f"SMS sent to {phone_number} (SID: {message.sid})")
            return {
                'success': True,
                'message_sid': message.sid,
                'to': phone_number
            }

        except TwilioException as e:
            logger.error(f"Twilio SMS error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _send_voice_notification(self, alert: AlertThreshold, alert_log: AlertLog, phone_number: str) -> Dict:
        """Send voice call notification for critical alerts"""
        try:
            if not self.twilio_client:
                return {'success': False, 'error': 'Twilio not configured'}

            # Create TwiML for voice message
            twiml_message = f"""
            <Response>
                <Say voice="alice">
                    This is a critical alert from the A-BAY Reservoir System.
                    {alert.name}.
                    {alert.parameter} is {alert_log.triggered_value:.1f}.
                    Please check the system immediately.
                </Say>
            </Response>
            """

            call = self.twilio_client.calls.create(
                twiml=twiml_message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )

            logger.info(f"Voice call initiated to {phone_number} (SID: {call.sid})")
            return {
                'success': True,
                'call_sid': call.sid,
                'to': phone_number
            }

        except TwilioException as e:
            logger.error(f"Twilio voice error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _send_browser_notification(self, alert: AlertThreshold, alert_log: AlertLog) -> Dict:
        """Send browser notification via WebSocket"""
        try:
            if not self.channel_layer:
                return {'success': False, 'error': 'Channel layer not available'}

            notification_data = {
                'type': 'alert_notification',
                'alert': {
                    'id': alert_log.id,
                    'name': alert.name,
                    'severity': alert.severity,
                    'parameter': alert.parameter,
                    'triggered_value': alert_log.triggered_value,
                    'threshold_value': alert.threshold_value,
                    'message': alert_log.message,
                    'timestamp': alert_log.created_at.isoformat()
                }
            }

            # Send to user's personal channel
            user_channel = f"user_{alert.user.id}"
            async_to_sync(self.channel_layer.group_send)(
                user_channel,
                {
                    'type': 'send_alert',
                    'data': notification_data
                }
            )

            logger.info(f"Browser notification sent for '{alert.name}'")
            return {'success': True}

        except Exception as e:
            logger.error(f"Failed to send browser notification: {str(e)}")
            return {'success': False, 'error': str(e)}

    def check_all_alerts(self, system_data: Dict = None) -> List[Dict]:
        """
        Enhanced to check both standard and special alerts
        """
        if system_data is None:
            system_data = self.fetch_current_pi_data()
            if not system_data:
                logger.error("No system data available for alert checking")
                return []

        triggered_alerts = []

        # Get all active alert thresholds
        active_alerts = AlertThreshold.objects.filter(
            is_active=True
        ).select_related('user', 'user__optimization_profile')

        logger.info(f"Checking {active_alerts.count()} active alerts...")

        # Separate standard and special alerts
        standard_alerts = active_alerts.filter(special_type='standard')
        special_alerts = active_alerts.exclude(special_type='standard')

        # Check standard alerts
        for alert in standard_alerts:
            try:
                parameter_value = system_data.get(alert.parameter)

                if parameter_value is None:
                    logger.debug(f"Parameter '{alert.parameter}' not found in system data for alert '{alert.name}'")
                    continue

                if alert.check_condition(parameter_value) and not alert.is_in_cooldown():
                    triggered_alert = self._trigger_alert(alert, parameter_value, system_data)
                    if triggered_alert:
                        triggered_alerts.append(triggered_alert)

            except Exception as e:
                logger.error(f"Error checking alert '{alert.name}': {str(e)}")

        # Check special alerts
        for alert in special_alerts:
            try:
                triggered, message = self._check_special_alert(alert, system_data)
                if triggered and not alert.is_in_cooldown():
                    # Get the relevant value for logging
                    triggered_value = system_data.get(alert.parameter, 0)

                    # Create custom alert log with special message
                    alert_log = AlertLog.objects.create(
                        user=alert.user,
                        alert_threshold=alert,
                        triggered_value=triggered_value,
                        message=message,
                        severity=alert.severity
                    )

                    # Update last triggered
                    alert.last_triggered = timezone.now()
                    alert.save()

                    # Send notifications
                    notification_results = self._send_notifications(alert, alert_log, system_data)

                    # Update log
                    alert_log.email_sent = notification_results.get('email', {}).get('success', False)
                    alert_log.sms_sent = notification_results.get('sms', {}).get('success', False)
                    alert_log.voice_sent = notification_results.get('voice', {}).get('success', False)
                    alert_log.browser_shown = notification_results.get('browser', {}).get('success', False)
                    alert_log.save()

                    triggered_alerts.append({
                        'alert_id': alert.id,
                        'alert_name': alert.name,
                        'user_id': alert.user.id,
                        'username': alert.user.username,
                        'parameter': alert.parameter,
                        'triggered_value': triggered_value,
                        'threshold_value': alert.threshold_value,
                        'condition': alert.condition,
                        'severity': alert.severity,
                        'message': message,
                        'timestamp': alert_log.created_at.isoformat(),
                        'notifications': notification_results,
                        'special_type': alert.special_type
                    })

            except Exception as e:
                logger.error(f"Error checking special alert '{alert.name}': {str(e)}")

        return triggered_alerts

    def _check_special_alert(self, alert: AlertThreshold, system_data: Dict) -> tuple[bool, Optional[str]]:
        """Check special alert types that require custom logic"""
        if alert.special_type == 'rafting_ramp':
            return self._check_rafting_ramp_alert(alert, system_data)
        elif alert.special_type == 'float_change':
            return self._check_float_change_alert(alert, system_data)
        elif alert.special_type == 'deviation':
            return self._check_deviation_alert(alert, system_data)
        else:
            return False, None

    def _check_rafting_ramp_alert(self, alert: AlertThreshold, system_data: Dict) -> tuple[bool, Optional[str]]:
        """Check if OXPH needs to be ramped for rafting schedule"""
        metadata = alert.metadata or {}

        # Get rafting schedule info
        start_time_str = metadata.get('start_time')
        ramp_up_buffer = metadata.get('ramp_up_buffer', 90)
        day = metadata.get('day', 'today')

        if not start_time_str:
            return False, None

        # Get current OXPH power
        current_oxph = system_data.get('oxph_power', 0)
        target_oxph = alert.threshold_value  # 5.8 MW for rafting

        # Check if we need to get OXPH setpoint from PI
        oxph_setpoint = system_data.get('oxph_setpoint')
        if oxph_setpoint is None:
            # Try to get from Afterbay_Elevation_Setpoint or similar
            oxph_setpoint = system_data.get('Oxbow_Power_Setpoint', current_oxph)

        # Calculate required ramp time based on constants
        ramp_rate = 0.042  # MW per minute (from your constants)
        mw_to_ramp = target_oxph - current_oxph

        if mw_to_ramp <= 0:
            return False, None  # Already at or above target

        ramp_time_needed = int(mw_to_ramp / ramp_rate)

        # Determine the target date
        now = timezone.now()
        if day == 'tomorrow':
            target_date = now.date() + timedelta(days=1)
        else:
            target_date = now.date()

        # Parse rafting start time
        try:
            rafting_start = datetime.strptime(
                f"{target_date} {start_time_str}",
                "%Y-%m-%d %H:%M"
            )
            # Make timezone aware (assuming Pacific time)
            rafting_start = timezone.make_aware(rafting_start)
        except ValueError:
            logger.error(f"Invalid rafting start time format: {start_time_str}")
            return False, None

        # Skip if rafting time has already passed
        if rafting_start < now:
            return False, None

        # Calculate when ramp should start
        ramp_start_time = rafting_start - timedelta(minutes=ramp_time_needed)
        alert_time = ramp_start_time - timedelta(minutes=ramp_up_buffer)

        # Check if we're in the alert window
        if alert_time <= now <= ramp_start_time:
            # Check if OXPH setpoint is still not adjusted
            if oxph_setpoint < (target_oxph - 0.1):  # Small tolerance
                minutes_until_rafting = int((rafting_start - now).total_seconds() / 60)
                minutes_until_ramp_needed = int((ramp_start_time - now).total_seconds() / 60)

                message = (
                    f"OXPH RAMP ALERT: Rafting starts at {start_time_str} "
                    f"({minutes_until_rafting} minutes). "
                    f"OXPH is at {current_oxph:.1f} MW (setpoint: {oxph_setpoint:.1f} MW) "
                    f"but needs to reach {target_oxph:.1f} MW. "
                    f"Ramp must start within {minutes_until_ramp_needed} minutes! "
                    f"Required ramp time: {ramp_time_needed} minutes."
                )

                return True, message

        return False, None

    def _check_float_change_alert(self, alert: AlertThreshold, system_data: Dict) -> tuple[bool, Optional[str]]:
        """Check if float level has changed significantly"""
        current_float = system_data.get('float_level')

        if current_float is None:
            # Try alternative parameter names
            current_float = system_data.get('Afterbay_Elevation_Setpoint')

        if current_float is None:
            return False, None

        if alert.last_known_value is None:
            # First time checking, just store the value
            alert.last_known_value = current_float
            alert.save(update_fields=['last_known_value'])
            logger.info(f"Initialized float level tracking at {current_float:.1f} ft")
            return False, None

        # Check change
        change = abs(current_float - alert.last_known_value)
        sensitivity = alert.threshold_value  # How much change triggers alert

        if change >= sensitivity:
            direction = "increased" if current_float > alert.last_known_value else "decreased"
            message = (
                f"FLOAT LEVEL CHANGE: Float level has {direction} from "
                f"{alert.last_known_value:.1f} ft to {current_float:.1f} ft "
                f"(change of {change:.1f} ft). "
                f"Time: {timezone.now().strftime('%H:%M')} PT"
            )

            # Update last known value
            alert.last_known_value = current_float
            alert.save(update_fields=['last_known_value'])

            return True, message

        return False, None

    def _check_deviation_alert(self, alert: AlertThreshold, system_data: Dict) -> tuple[bool, Optional[str]]:
        """Check if OXPH deviates from setpoint"""
        current_oxph = system_data.get('oxph_power')
        oxph_setpoint = system_data.get('oxph_setpoint')

        # Try alternative names if needed
        if current_oxph is None:
            current_oxph = system_data.get('Oxbow_Power')
        if oxph_setpoint is None:
            oxph_setpoint = system_data.get('Oxbow_Power_Setpoint')

        if current_oxph is None or oxph_setpoint is None:
            logger.debug(f"Missing data for deviation check - OXPH: {current_oxph}, Setpoint: {oxph_setpoint}")
            return False, None

        deviation = abs(current_oxph - oxph_setpoint)
        max_deviation = alert.threshold_value

        if deviation > max_deviation:
            direction = "above" if current_oxph > oxph_setpoint else "below"
            message = (
                f"OXPH DEVIATION: Current output is {current_oxph:.1f} MW, "
                f"{direction} setpoint of {oxph_setpoint:.1f} MW "
                f"(deviation of {deviation:.1f} MW exceeds limit of {max_deviation:.1f} MW). "
                f"Time: {timezone.now().strftime('%H:%M')} PT"
            )
            return True, message

        return False, None

    def fetch_current_pi_data(self) -> Optional[Dict]:
        """
        Enhanced to include OXPH setpoint for deviation alerts
        """
        try:
            logger.info("Fetching current PI data...")
            use_simulated = settings.ABAY_OPTIMIZATION.get('USE_SIMULATED_DATA', False)

            if use_simulated:
                logger.info("USE_SIMULATED_DATA is True - using simulated PI data")
                return self._get_simulated_pi_data()

            # Check if data_fetcher was imported successfully
            if 'data_fetcher' not in globals():
                logger.error("data_fetcher module not imported - using simulated data")
                return self._get_simulated_pi_data()  # You'll need to add this fallback method

            # Use your existing data_fetcher to get current state
            current_state, _ = data_fetcher.get_historical_and_current_data()

            if not current_state:
                logger.error("No current state data returned from PI")
                return None

            logger.info(f"Successfully fetched PI data: {list(current_state.keys())}")

            # Map PI data to alerting parameter names
            pi_data = {
                'afterbay_elevation': current_state.get('Afterbay_Elevation'),
                'oxph_power': current_state.get('Oxbow_Power'),
                'oxph_setpoint': current_state.get('Oxbow_Power_Setpoint'),  # Add setpoint
                'r4_flow': current_state.get('R4_Flow'),
                'r30_flow': current_state.get('R30_Flow'),
                'r20_flow': current_state.get('R20_Flow'),
                'r5l_flow': current_state.get('R5L_Flow'),
                'r26_flow': current_state.get('R26_Flow'),
                'mfra_power': current_state.get('MFP_Total_Gen_GEN_MDFK_and_RA'),
                'float_level': current_state.get('Afterbay_Elevation_Setpoint'),
                'ccs_mode': current_state.get('CCS_Mode'),
                'timestamp': current_state.get('Timestamp_UTC')
            }

            # Calculate derived values
            if pi_data.get('r20_flow') and pi_data.get('r5l_flow'):
                pi_data['net_flow'] = pi_data['r20_flow'] - pi_data['r5l_flow']

            # Calculate spillage if you have the necessary data
            # This is a simplified example - adjust based on your actual spillage calculation
            if pi_data.get('afterbay_elevation') and pi_data.get('afterbay_elevation') > 1175.0:
                # Simple spillage estimate based on elevation
                pi_data['spillage'] = (pi_data['afterbay_elevation'] - 1175.0) * 100  # AF
            else:
                pi_data['spillage'] = 0

            # Remove None values
            pi_data = {k: v for k, v in pi_data.items() if v is not None}

            logger.info(f"Successfully fetched {len(pi_data)} PI data points")
            return pi_data

        except Exception as e:
            logger.error(f"Error fetching PI data: {str(e)}")
            return None

    def create_alert_log(self, alert_threshold: AlertThreshold, triggered_value: float, message: str) -> AlertLog:
        """Helper method to create alert log (for special alerts)"""
        return AlertLog.objects.create(
            user=alert_threshold.user,
            alert_threshold=alert_threshold,
            triggered_value=triggered_value,
            message=message,
            severity=alert_threshold.severity
        )

    def send_alert_notifications(self, alert_log: AlertLog) -> Dict:
        """Public method to send notifications for an alert log"""
        alert = alert_log.alert_threshold
        system_data = self.fetch_current_pi_data() or {}
        return self._send_notifications(alert, alert_log, system_data)

# Singleton instance
alerting_service = AlertingService()