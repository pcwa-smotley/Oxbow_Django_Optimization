# django_backend/optimization_api/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    AlertThreshold, AlertLog, UserProfile,
    OptimizationRun, ParameterSet, OptimizationResult, UserPreferences
)



class ParameterSetSerializer(serializers.ModelSerializer):
    """Serializer for parameter sets"""

    class Meta:
        model = ParameterSet
        fields = [
            'id', 'name', 'description', 'is_default', 'created_at', 'updated_at',
            'abay_min_elev_ft', 'abay_max_elev_buffer_ft', 'abay_elev_ft_per_af',
            'oxph_min_mw', 'oxph_max_mw', 'oxph_ramp_rate_mw_per_min',
            'lp_spillage_penalty_weight', 'lp_summer_mw_reward_weight',
            'lp_base_smoothing_penalty_weight', 'lp_target_elev_midpoint_weight',
            'summer_start_month', 'summer_start_day', 'summer_target_start_time',
            'summer_target_end_time', 'summer_oxph_target_mw'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Create a new parameter set"""
        # Set the created_by field if user is authenticated
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class OptimizationRunSerializer(serializers.ModelSerializer):
    """Serializer for optimization runs"""

    run_mode_display = serializers.CharField(source='get_run_mode_display', read_only=True)
    optimizer_type_display = serializers.CharField(source='get_optimizer_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    parameter_set_name = serializers.CharField(source='parameter_set.name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = OptimizationRun
        fields = [
            'id', 'run_mode', 'run_mode_display', 'optimizer_type', 'optimizer_type_display',
            'forecast_source', 'created_at', 'started_at', 'completed_at', 'historical_start_date',
            'status', 'status_display', 'progress_message', 'progress_percentage',
            'parameter_set', 'parameter_set_name', 'custom_parameters', 'task_id',
            'result_file_path', 'error_message', 'total_spillage_af', 'avg_oxph_utilization_pct',
            'peak_elevation_ft', 'min_elevation_ft', 'r_bias_cfs', 'created_by_username',
            'duration_seconds'
        ]
        read_only_fields = [
            'id', 'created_at', 'started_at', 'completed_at', 'task_id', 'result_file_path',
            'error_message', 'total_spillage_af', 'avg_oxph_utilization_pct',
            'peak_elevation_ft', 'min_elevation_ft', 'r_bias_cfs', 'duration_seconds'
        ]

    def get_duration_seconds(self, obj):
        """Calculate the duration of the optimization run in seconds"""
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        elif obj.started_at:
            from django.utils import timezone
            return (timezone.now() - obj.started_at).total_seconds()
        return None

    def create(self, validated_data):
        """Create a new optimization run"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class OptimizationResultSerializer(serializers.ModelSerializer):
    """Serializer for detailed optimization results"""

    timestamp_pt = serializers.SerializerMethodField()

    class Meta:
        model = OptimizationResult
        fields = [
            'timestamp_utc', 'timestamp_pt',
            # Input data
            'r4_flow_cfs', 'r30_flow_cfs', 'mfra_mw',
            'r20_minus_r5l_cfs', 'r5l_flow_cfs', 'r26_flow_cfs', 'ccs_mode', 'abay_float_ft',
            # Optimization results
            'oxph_generation_mw', 'abay_elev_ft', 'abay_af',
            # Diagnostic data
            'mf1_2_mw', 'mf1_2_cfs', 'oxph_outflow_cfs', 'abay_delta_af',
            'abay_net_flow_cfs', 'spill_volume_af',
            # Setpoint guidance
            'adjust_oxph_needed', 'oxph_setpoint_target', 'setpoint_adjust_time_pt',
            'is_head_loss_limited',
            # Historical comparison
            'actual_oxph_mw', 'actual_abay_elev_ft', 'abay_error_af', 'abay_error_cfs'
        ]

    def get_timestamp_pt(self, obj):
        """Convert UTC timestamp to Pacific Time for display"""
        if obj.timestamp_utc:
            import pytz
            pacific_tz = pytz.timezone('America/Los_Angeles')
            return obj.timestamp_utc.replace(tzinfo=pytz.UTC).astimezone(pacific_tz).isoformat()
        return None


class UserPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for user preferences"""

    class Meta:
        model = UserPreferences
        fields = [
            'default_parameter_set', 'default_forecast_source', 'default_optimizer_type',
            'dashboard_refresh_interval_seconds', 'show_advanced_diagnostics',
            'email_notifications', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class OptimizationRequestSerializer(serializers.Serializer):
    """Serializer for optimization run requests"""

    run_mode = serializers.ChoiceField(
        choices=['forecast', 'historical'],
        default='forecast'
    )
    optimizer_type = serializers.ChoiceField(
        choices=['linear', 'heuristic'],
        default='linear'
    )
    forecast_source = serializers.ChoiceField(
        choices=['hydroforecast-short-term', 'cnrfc'],
        default='hydroforecast-short-term'
    )
    historical_start_date = serializers.DateField(required=False, allow_null=True)
    parameter_set_id = serializers.IntegerField(required=False, allow_null=True)
    custom_parameters = serializers.DictField(required=False, allow_empty=True, default=dict)

    def validate(self, data):
        """Validate the optimization request"""
        # Check if historical date is provided for historical mode
        if data.get('run_mode') == 'historical' and not data.get('historical_start_date'):
            raise serializers.ValidationError(
                "historical_start_date is required for historical simulation mode"
            )

        # Validate parameter set exists if provided
        if data.get('parameter_set_id'):
            try:
                ParameterSet.objects.get(id=data['parameter_set_id'])
            except ParameterSet.DoesNotExist:
                raise serializers.ValidationError(
                    f"Parameter set with id {data['parameter_set_id']} does not exist"
                )

        # Validate custom parameters
        custom_params = data.get('custom_parameters', {})
        if custom_params:
            # Define allowed parameter keys and their types
            allowed_params = {
                'ABAY_MIN_ELEV_FT': float,
                'ABAY_MAX_ELEV_BUFFER_FT': float,
                'OXPH_MIN_MW': float,
                'OXPH_MAX_MW': float,
                'OXPH_RAMP_RATE_MW_PER_MIN': float,
                'LP_SPILLAGE_PENALTY_WEIGHT': float,
                'LP_SUMMER_MW_REWARD_WEIGHT': float,
                'LP_BASE_SMOOTHING_PENALTY_WEIGHT': float,
                'SUMMER_OXPH_TARGET_MW': float,
                'SUMMER_START_MONTH': int,
                'SUMMER_START_DAY': int,
            }

            for param_name, param_value in custom_params.items():
                if param_name not in allowed_params:
                    raise serializers.ValidationError(
                        f"Parameter '{param_name}' is not allowed in custom_parameters"
                    )

                expected_type = allowed_params[param_name]
                try:
                    # Attempt to convert to expected type
                    if expected_type == float:
                        float(param_value)
                    elif expected_type == int:
                        int(param_value)
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"Parameter '{param_name}' must be of type {expected_type.__name__}"
                    )

        return data


class RecalculateElevationRequestSerializer(serializers.Serializer):
    """Serializer for elevation recalculation requests"""

    forecast_data = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        help_text="List of forecast data points with 'mfra', 'oxph', 'r4', 'r30' keys"
    )

    def validate_forecast_data(self, value):
        """Validate forecast data structure"""
        required_fields = ['mfra', 'oxph', 'r4', 'r30']

        for i, data_point in enumerate(value):
            for field in required_fields:
                if field not in data_point:
                    raise serializers.ValidationError(
                        f"Missing required field '{field}' in forecast_data item {i}"
                    )

                # Validate that values are numeric
                try:
                    float(data_point[field])
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"Field '{field}' in forecast_data item {i} must be numeric"
                    )

        return value


class HistoricalDataRequestSerializer(serializers.Serializer):
    """Serializer for historical data requests"""

    start_date = serializers.DateField(
        help_text="Start date for historical data (YYYY-MM-DD)"
    )
    end_date = serializers.DateField(
        help_text="End date for historical data (YYYY-MM-DD)"
    )
    include_forecasts = serializers.BooleanField(
        default=False,
        help_text="Include forecast data in addition to actual data"
    )
    data_types = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'elevation', 'oxph_power', 'flows', 'generation', 'all'
        ]),
        default=['all'],
        help_text="Types of data to include"
    )

    def validate(self, data):
        """Validate the historical data request"""
        start_date = data['start_date']
        end_date = data['end_date']

        if start_date >= end_date:
            raise serializers.ValidationError(
                "start_date must be before end_date"
            )

        # Limit the date range to prevent excessive queries
        from datetime import timedelta
        max_range = timedelta(days=30)  # 30 days max
        if end_date - start_date > max_range:
            raise serializers.ValidationError(
                f"Date range cannot exceed {max_range.days} days"
            )

        return data


class DashboardDataSerializer(serializers.Serializer):
    """Serializer for dashboard data response"""

    current_state = serializers.DictField()
    recent_runs = OptimizationRunSerializer(many=True)
    chart_data = serializers.DictField(allow_null=True)
    system_status = serializers.CharField()
    alerts = serializers.ListField(child=serializers.DictField())
    statistics = serializers.DictField()


class OptimizationStatusSerializer(serializers.Serializer):
    """Serializer for optimization status response"""

    run_id = serializers.IntegerField()
    task_id = serializers.CharField()
    status = serializers.CharField()
    progress_message = serializers.CharField()
    progress_percentage = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    task_status = serializers.CharField()
    task_info = serializers.DictField(required=False)
    task_result = serializers.DictField(required=False)
    task_error = serializers.CharField(required=False)
    summary = serializers.DictField(required=False)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'user', 'phone_number', 'email_notifications',
            'sms_notifications', 'browser_notifications',
            'dark_mode', 'default_tab', 'refresh_interval'
        ]


class AlertThresholdSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True
    )
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AlertThreshold
        fields = [
            'id', 'user', 'username', 'name', 'description',
            'parameter', 'condition', 'threshold_value',
            'threshold_value_max', 'severity', 'is_active',
            'email_notification', 'sms_notification',
            'voice_notification', 'browser_notification',
            'cooldown_minutes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate alert threshold data"""
        condition = data.get('condition')
        threshold_max = data.get('threshold_value_max')

        # Validate range conditions have max value
        if condition in ['between', 'outside_range'] and not threshold_max:
            raise serializers.ValidationError(
                "threshold_value_max is required for range conditions"
            )

        # Validate threshold values make sense
        if threshold_max and threshold_max <= data.get('threshold_value'):
            raise serializers.ValidationError(
                "threshold_value_max must be greater than threshold_value"
            )

        return data


class AlertLogSerializer(serializers.ModelSerializer):
    alert_name = serializers.CharField(source='alert_threshold.name', read_only=True)
    parameter = serializers.CharField(source='alert_threshold.parameter', read_only=True)

    class Meta:
        model = AlertLog
        fields = [
            'id', 'alert_name', 'parameter', 'triggered_value',
            'message', 'severity', 'created_at', 'acknowledged',
            'acknowledged_at', 'email_sent', 'sms_sent',
            'voice_sent', 'browser_shown'
        ]
        read_only_fields = ['id', 'created_at']


# Update your existing serializers if needed:
