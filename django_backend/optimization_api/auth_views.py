# django_backend/optimization_api/auth_views.py

import logging
from datetime import timedelta
from django.utils import timezone  # Fix: timezone should be from django.utils
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.views import LoginView as BaseLoginView
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.contrib import messages
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.conf import settings


from .models import UserProfile, ParameterSet, AlertThreshold, AlertLog
from .serializers import (
    UserSerializer, UserProfileSerializer,
    AlertThresholdSerializer, AlertLogSerializer
)

logger = logging.getLogger(__name__)


@api_view(['GET'])
def auth_status(request):
    """Check if user is authenticated"""
    if request.user.is_authenticated:
        # Update last activity
        try:
            profile = request.user.optimization_profile
            profile.last_activity = timezone.now()
            profile.save(update_fields=['last_activity'])
        except:
            pass

        return Response({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name
            }
        })
    return Response({'authenticated': False})


@method_decorator(csrf_protect, name='dispatch')
class CustomLoginView(BaseLoginView):
    """Custom login view with remember me functionality"""
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        """Handle successful login with remember me option"""
        # Get remember me value from POST data
        remember_me = self.request.POST.get('remember_me', None)

        # Authenticate user
        user = form.get_user()
        auth_login(self.request, user)

        # Update user profile last_login
        try:
            profile = user.optimization_profile
            profile.last_login = timezone.now()
            profile.save(update_fields=['last_login'])
        except:
            pass

        # Set session expiry based on remember me
        if remember_me:
            # Set session to expire in 7 days
            self.request.session.set_expiry(60 * 60 * 24 * 7)  # 7 days in seconds
            # Set a flag to indicate long session
            self.request.session['remembered'] = True
        else:
            # Session expires when browser closes
            self.request.session.set_expiry(0)
            self.request.session['remembered'] = False

        # Log the login event
        logger.info(f"User {user.username} logged in with remember_me={bool(remember_me)}")

        # Show welcome message
        messages.success(
            self.request,
            f"Welcome back, {user.first_name or user.username}!"
        )

        return super().form_valid(form)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        """Handle user login via API"""
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({
                'error': 'Username and password required'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            # Get user's default parameters if any
            default_params = None
            try:
                default_param_set = ParameterSet.objects.filter(
                    created_by=user,
                    is_default=True
                ).first()
                if default_param_set:
                    default_params = default_param_set.parameters
            except Exception as e:
                logger.error(f"Error loading default parameters: {e}")

            return Response({
                'status': 'success',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'default_parameters': default_params
                }
            })

        return Response({
            'error': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    def post(self, request):
        """Handle user logout"""
        logout(request)
        return Response({'status': 'success'})


class RegistrationDisabledView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'error': 'Registration is disabled',
            'message': 'Please contact the system administrator for access'
        }, status=status.HTTP_403_FORBIDDEN)

    def post(self, request):
        return self.get(request)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user profile"""
        try:
            profile = request.user.optimization_profile
            return Response({
                'status': 'success',
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'email': request.user.email,
                    'profile': {
                        'phone_number': profile.phone_number,
                        'email_notifications': profile.email_notifications,
                        'sms_notifications': profile.sms_notifications,
                        'browser_notifications': profile.browser_notifications,
                        'dark_mode': profile.dark_mode,
                        'default_tab': profile.default_tab,
                        'refresh_interval': profile.refresh_interval,
                    }
                }
            })
        except UserProfile.DoesNotExist:
            return Response({
                'error': 'Profile not found'
            }, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        """Update user profile"""
        try:
            profile = request.user.optimization_profile

            # Update profile fields
            for field in ['phone_number', 'email_notifications', 'sms_notifications',
                          'browser_notifications', 'dark_mode', 'default_tab', 'refresh_interval']:
                if field in request.data:
                    setattr(profile, field, request.data[field])

            profile.save()

            return Response({
                'status': 'success',
                'message': 'Profile updated successfully'
            })

        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return Response({
                'error': 'Failed to update profile'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ParametersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user's parameter sets"""
        param_sets = ParameterSet.objects.filter(
            created_by=request.user
        ).order_by('-is_default', '-created_at')

        return Response({
            'status': 'success',
            'parameters': [{
                'id': ps.id,
                'name': ps.name,
                'description': ps.description,
                'is_default': ps.is_default,
                'created_at': ps.created_at,
                **ps.parameters
            } for ps in param_sets]
        })

    def post(self, request):
        """Create new parameter set"""
        try:
            name = request.data.get('name', 'Unnamed Parameters')
            description = request.data.get('description', '')
            is_default = request.data.get('is_default', False)

            # Extract parameter values
            param_fields = [
                'ABAY_MIN_ELEV_FT', 'LP_SPILLAGE_PENALTY_WEIGHT',
                'SUMMER_TARGET_START_TIME', 'SUMMER_OXPH_TARGET_MW',
                'minElevation', 'spillagePenalty', 'summerStartTime', 'summerTargetMW'
            ]

            parameters = {}
            for field in param_fields:
                if field in request.data:
                    parameters[field] = request.data[field]

            # If marking as default, unset other defaults
            if is_default:
                ParameterSet.objects.filter(
                    created_by=request.user,
                    is_default=True
                ).update(is_default=False)

            param_set = ParameterSet.objects.create(
                name=name,
                description=description,
                parameters=parameters,
                is_default=is_default,
                created_by=request.user
            )

            return Response({
                'status': 'success',
                'parameters': parameters,
                'id': param_set.id
            })

        except Exception as e:
            logger.error(f"Parameter save error: {e}")
            return Response({
                'error': 'Failed to save parameters'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AlertsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user's alert thresholds"""
        alerts = AlertThreshold.objects.filter(
            user=request.user
        ).order_by('-is_active', '-created_at')

        alert_data = []
        for alert in alerts:
            data = AlertThresholdSerializer(alert).data
            # Add last triggered info
            if alert.last_triggered:
                data['last_triggered'] = alert.last_triggered.isoformat()
            alert_data.append(data)

        return Response({
            'status': 'success',
            'alerts': alert_data
        })

    def post(self, request):
        """Create new alert threshold"""
        try:
            data = request.data.copy()
            data['user'] = request.user.id

            serializer = AlertThresholdSerializer(data=data)
            if serializer.is_valid():
                alert = serializer.save()

                logger.info(f"Alert created: {alert.name} for user {request.user.username}")

                return Response({
                    'status': 'success',
                    'alert': serializer.data
                })

            return Response({
                'error': 'Invalid alert data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Alert creation error: {e}")
            return Response({
                'error': 'Failed to create alert'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AlertDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, alert_id):
        """Get alert object if user owns it"""
        try:
            return AlertThreshold.objects.get(
                id=alert_id,
                user=self.request.user  # Fix: use self.request.user
            )
        except AlertThreshold.DoesNotExist:
            return None

    def put(self, request, alert_id):
        """Update alert threshold"""
        alert = self.get_object(alert_id)
        if not alert:
            return Response({
                'error': 'Alert not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = AlertThresholdSerializer(
            alert,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'alert': serializer.data
            })

        return Response({
            'error': 'Invalid data',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, alert_id):
        """Delete alert threshold"""
        alert = self.get_object(alert_id)
        if not alert:
            return Response({
                'error': 'Alert not found'
            }, status=status.HTTP_404_NOT_FOUND)

        alert_name = alert.name
        alert.delete()

        logger.info(f"Alert deleted: {alert_name} by user {request.user.username}")

        return Response({
            'status': 'success',
            'message': f'Alert "{alert_name}" deleted'
        })


class AlertHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user's alert history"""
        days = int(request.query_params.get('days', 7))

        since = timezone.now() - timedelta(days=days)

        logs = AlertLog.objects.filter(
            user=request.user,
            created_at__gte=since
        ).order_by('-created_at')[:100]

        return Response({
            'status': 'success',
            'history': AlertLogSerializer(logs, many=True).data,
            'count': logs.count()
        })


@api_view(['POST'])
@csrf_protect
def activity_ping(request):
    """Update user's last activity timestamp"""
    if request.user.is_authenticated:
        try:
            profile = request.user.optimization_profile
            profile.last_activity = timezone.now()
            profile.save(update_fields=['last_activity'])
            return Response({'status': 'success'})
        except:
            pass
    return Response({'status': 'error'}, status=status.HTTP_400_BAD_REQUEST)


class EnhancedAlertsView(APIView):
    """Enhanced alerts API with category support"""

    def get(self, request):
        """Get user's alerts organized by category"""
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)

        try:
            alerts = AlertThreshold.objects.filter(user=request.user)

            # Organize alerts by category
            categorized_alerts = {
                'flow': [],
                'afterbay': [],
                'rafting': [],
                'generation': [],
                'general': []
            }

            for alert in alerts:
                alert_data = alert.to_dict()
                category = alert.category or 'general'
                if category in categorized_alerts:
                    categorized_alerts[category].append(alert_data)

            return Response({
                'status': 'success',
                'alerts': list(alerts.values()),  # For backward compatibility
                'categorized_alerts': categorized_alerts,
                'total_count': alerts.count(),
                'active_count': alerts.filter(is_active=True).count()
            })

        except Exception as e:
            return Response({
                'status': 'error',
                'error': str(e)
            }, status=500)

    def post(self, request):
        """Create new alert with enhanced features"""
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)

        try:
            data = request.data

            # Handle special alert types
            special_type = data.get('special_type', 'standard')
            category = data.get('category', 'general')

            # Create alert
            alert = AlertThreshold.objects.create(
                user=request.user,
                name=data['name'],
                parameter=data['parameter'],
                condition=data.get('condition', 'greater_than'),
                threshold_value=float(data['threshold_value']),
                threshold_value_max=float(data['threshold_value_max']) if data.get('threshold_value_max') else None,
                severity=data.get('severity', 'warning'),
                category=category,
                special_type=special_type,
                metadata=data.get('metadata', {}),
                email_notification=data.get('email_notification', True),
                browser_notification=data.get('browser_notification', True),
                sms_notification=data.get('sms_notification', False),
                is_active=data.get('is_active', True),
                cooldown_minutes=data.get('cooldown_minutes', 30)
            )

            return Response({
                'status': 'success',
                'alert': alert.to_dict()
            }, status=201)

        except Exception as e:
            return Response({
                'status': 'error',
                'error': str(e)
            }, status=400)

    def put(self, request, alert_id):
        """Update existing alert"""
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)

        try:
            alert = AlertThreshold.objects.get(id=alert_id, user=request.user)
            data = request.data

            # Update fields
            for field in ['name', 'parameter', 'condition', 'severity', 'category',
                          'special_type', 'metadata', 'is_active', 'cooldown_minutes',
                          'email_notification', 'browser_notification', 'sms_notification']:
                if field in data:
                    setattr(alert, field, data[field])

            if 'threshold_value' in data:
                alert.threshold_value = float(data['threshold_value'])
            if 'threshold_value_max' in data:
                alert.threshold_value_max = float(data['threshold_value_max']) if data['threshold_value_max'] else None

            alert.save()

            return Response({
                'status': 'success',
                'alert': alert.to_dict()
            })

        except AlertThreshold.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Alert not found'
            }, status=404)
        except Exception as e:
            return Response({
                'status': 'error',
                'error': str(e)
            }, status=400)


@login_required
@require_http_methods(["GET"])
def get_alert_history(request):
    """Get recent alert history for the user"""
    try:
        # Get last 50 alert logs for the user
        logs = AlertLog.objects.filter(
            user=request.user
        ).select_related('alert_threshold').order_by('-created_at')[:50]

        history = []
        for log in logs:
            history.append({
                'id': log.id,
                'alert_name': log.alert_threshold.name,
                'parameter': log.alert_threshold.parameter,
                'triggered_value': log.triggered_value,
                'threshold_value': log.alert_threshold.threshold_value,
                'message': log.message,
                'severity': log.severity,
                'acknowledged': log.acknowledged,
                'created_at': log.created_at.isoformat()
            })

        return JsonResponse({
            'status': 'success',
            'history': history
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_alert(request, alert_id):
    """Test an alert by triggering it manually"""
    try:
        alert = AlertThreshold.objects.get(id=alert_id, user=request.user)

        # Create a test alert log
        from optimization_api.alerting import alerting_service

        test_value = alert.threshold_value * 1.1  # Simulate exceeding threshold

        log = alerting_service.create_alert_log(
            alert_threshold=alert,
            triggered_value=test_value,
            message=f"TEST: {alert.name} threshold exceeded (test mode)"
        )

        # Send notifications
        alerting_service.send_alert_notifications(log)

        return JsonResponse({
            'status': 'success',
            'message': 'Test alert sent successfully'
        })

    except AlertThreshold.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error': 'Alert not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


# Add this to django_backend/optimization_api/auth_views.py

@login_required
@require_http_methods(["POST"])
def test_notifications(request):
    """Test notification system without triggering actual alerts"""
    try:
        notification_type = request.POST.get('notification_type', 'browser')

        # Get user profile
        profile = request.user.optimization_profile
        results = {}

        # Import alerting service
        from optimization_api.alerting import alerting_service

        # Test based on notification type
        if notification_type == 'browser':
            # Send test browser notification via WebSocket
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync

                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{request.user.id}",
                        {
                            'type': 'send_alert',
                            'data': {
                                'type': 'alert_notification',
                                'alert': {
                                    'id': 'test',
                                    'name': 'Test Browser Notification',
                                    'severity': 'info',
                                    'parameter': 'test',
                                    'message': 'This is a test browser notification from ABAY Alerts',
                                    'timestamp': timezone.now().isoformat(),
                                    'is_test': True
                                }
                            }
                        }
                    )
                    results['browser'] = {
                        'success': True,
                        'message': 'Test browser notification sent'
                    }
                else:
                    results['browser'] = {
                        'success': False,
                        'message': 'WebSocket channel layer not available'
                    }
            except Exception as e:
                results['browser'] = {
                    'success': False,
                    'message': f'Browser notification error: {str(e)}'
                }

        elif notification_type == 'email':
            # Test email
            if not request.user.email:
                results['email'] = {
                    'success': False,
                    'message': 'No email address configured for your account'
                }
            else:
                try:
                    from django.core.mail import send_mail

                    send_mail(
                        subject='ABAY Alerts - Test Email Notification',
                        message=f"""This is a test email from the ABAY Reservoir Optimization Alert System.

If you're receiving this email, your email notifications are working correctly.

User: {request.user.username}
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} PT

This is only a test. No action is required.

To manage your notification preferences, visit: {settings.SITE_URL}/profile""",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[request.user.email],
                        fail_silently=False
                    )

                    results['email'] = {
                        'success': True,
                        'message': f'Test email sent to {request.user.email}'
                    }
                except Exception as e:
                    results['email'] = {
                        'success': False,
                        'message': f'Email error: {str(e)}'
                    }

        elif notification_type == 'sms':
            # Test SMS
            if not profile.phone_number:
                results['sms'] = {
                    'success': False,
                    'message': 'No phone number configured in your profile'
                }
            elif not alerting_service.twilio_client:
                results['sms'] = {
                    'success': False,
                    'message': 'SMS service not configured (Twilio)'
                }
            else:
                try:
                    message = alerting_service.twilio_client.messages.create(
                        body="ABAY Alerts Test: This is a test SMS notification. Your SMS alerts are working correctly.",
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=profile.phone_number
                    )

                    results['sms'] = {
                        'success': True,
                        'message': f'Test SMS sent to {profile.phone_number}',
                        'sid': message.sid
                    }
                except Exception as e:
                    results['sms'] = {
                        'success': False,
                        'message': f'SMS error: {str(e)}'
                    }

        elif notification_type == 'voice':
            # Test voice call
            if not profile.phone_number:
                results['voice'] = {
                    'success': False,
                    'message': 'No phone number configured in your profile'
                }
            elif not alerting_service.twilio_client:
                results['voice'] = {
                    'success': False,
                    'message': 'Voice service not configured (Twilio)'
                }
            else:
                try:
                    twiml_message = """
                    <Response>
                        <Say voice="alice">
                            This is a test call from the A-BAY Reservoir Alert System.
                            Your voice notifications are working correctly.
                            This is only a test. No action is required.
                            Thank you.
                        </Say>
                    </Response>
                    """

                    call = alerting_service.twilio_client.calls.create(
                        twiml=twiml_message,
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=profile.phone_number
                    )

                    results['voice'] = {
                        'success': True,
                        'message': f'Test call initiated to {profile.phone_number}',
                        'sid': call.sid
                    }
                except Exception as e:
                    results['voice'] = {
                        'success': False,
                        'message': f'Voice call error: {str(e)}'
                    }

        else:
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid notification type'
            }, status=400)

        # Log the test
        logger.info(f"Notification test performed by {request.user.username}: {notification_type}")

        return JsonResponse({
            'status': 'success',
            'notification_type': notification_type,
            'results': results,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in test_notifications: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)