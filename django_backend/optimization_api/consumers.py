# django_backend/optimization_api/consumers.py

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time alerts"""

    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            logger.warning("Anonymous user attempted WebSocket connection")
            await self.close()
            return

        # Join user-specific group
        self.user_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket connected for user: {self.user.username}")

        # Send initial connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to ABAY alerting system',
            'user_id': self.user.id,
            'timestamp': timezone.now().isoformat()
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

        logger.info(f"WebSocket disconnected for user: {getattr(self.user, 'username', 'unknown')}")

    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))

            elif message_type == 'acknowledge_alert':
                alert_id = data.get('alert_id')
                if alert_id:
                    await self.acknowledge_alert(alert_id)

            elif message_type == 'request_system_status':
                await self.send_system_status()

        except json.JSONDecodeError:
            logger.error("Invalid JSON received from WebSocket")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {str(e)}")

    async def send_alert(self, event):
        """Send alert notification to client"""
        await self.send(text_data=json.dumps(event['data']))

    async def send_system_update(self, event):
        """Send system status update to client"""
        await self.send(text_data=json.dumps(event['data']))

    @database_sync_to_async
    def acknowledge_alert(self, alert_id):
        """Mark alert as acknowledged in database"""
        try:
            from .models import AlertLog
            alert_log = AlertLog.objects.get(
                id=alert_id,
                user=self.user,
                acknowledged=False
            )
            alert_log.acknowledged = True
            alert_log.acknowledged_at = timezone.now()
            alert_log.save()

            logger.info(f"Alert {alert_id} acknowledged by user {self.user.username}")

        except AlertLog.DoesNotExist:
            logger.warning(f"Alert {alert_id} not found or already acknowledged")
        except Exception as e:
            logger.error(f"Error acknowledging alert {alert_id}: {str(e)}")

    async def send_system_status(self):
        """Send current system status to client"""
        try:
            from .models import SystemStatus

            # Get latest system status
            latest_status = await database_sync_to_async(
                lambda: SystemStatus.objects.first()
            )()

            if latest_status:
                status_data = {
                    'type': 'system_status',
                    'data': {
                        'status': latest_status.status,
                        'pi_data_available': latest_status.pi_data_available,
                        'alert_system_active': latest_status.alert_system_active,
                        'last_update': latest_status.created_at.isoformat()
                    }
                }
            else:
                status_data = {
                    'type': 'system_status',
                    'data': {
                        'status': 'unknown',
                        'message': 'No status information available'
                    }
                }

            await self.send(text_data=json.dumps(status_data))

        except Exception as e:
            logger.error(f"Error sending system status: {str(e)}")