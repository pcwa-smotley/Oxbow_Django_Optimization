# django_backend/optimization_api/models.py
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
import json
from django.utils import timezone



class ParameterSet(models.Model):
    """Stores optimization parameter configurations"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Reservoir Constants
    abay_min_elev_ft = models.FloatField(default=1168.0)
    abay_max_elev_buffer_ft = models.FloatField(default=0.3)
    abay_elev_ft_per_af = models.FloatField(default=0.0132)

    # OXPH Generator Constants
    oxph_min_mw = models.FloatField(default=0.8)
    oxph_max_mw = models.FloatField(default=5.8)
    oxph_ramp_rate_mw_per_min = models.FloatField(default=0.042)

    # Linear Programming Weights
    lp_spillage_penalty_weight = models.FloatField(default=10000.0)
    lp_summer_mw_reward_weight = models.FloatField(default=1000.0)
    lp_base_smoothing_penalty_weight = models.FloatField(default=100.0)
    lp_target_elev_midpoint_weight = models.FloatField(default=0.01)

    # Summer Schedule
    summer_start_month = models.IntegerField(default=6)
    summer_start_day = models.IntegerField(default=1)
    summer_target_start_time = models.TimeField(default='08:00:00')
    summer_target_end_time = models.TimeField(default='12:00:00')
    summer_oxph_target_mw = models.FloatField(default=5.8)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({'Default' if self.is_default else 'Custom'})"

    def to_dict(self):
        """Convert to dictionary for optimization engine"""
        return {
            'ABAY_MIN_ELEV_FT': self.abay_min_elev_ft,
            'ABAY_MAX_ELEV_BUFFER_FT': self.abay_max_elev_buffer_ft,
            'ABAY_ELEV_FT_PER_AF': self.abay_elev_ft_per_af,
            'OXPH_MIN_MW': self.oxph_min_mw,
            'OXPH_MAX_MW': self.oxph_max_mw,
            'OXPH_RAMP_RATE_MW_PER_MIN': self.oxph_ramp_rate_mw_per_min,
            'LP_SPILLAGE_PENALTY_WEIGHT': self.lp_spillage_penalty_weight,
            'LP_SUMMER_MW_REWARD_WEIGHT': self.lp_summer_mw_reward_weight,
            'LP_BASE_SMOOTHING_PENALTY_WEIGHT': self.lp_base_smoothing_penalty_weight,
            'LP_TARGET_ELEV_MIDPOINT_WEIGHT': self.lp_target_elev_midpoint_weight,
            'SUMMER_START_MONTH': self.summer_start_month,
            'SUMMER_START_DAY': self.summer_start_day,
            'SUMMER_TARGET_START_TIME': self.summer_target_start_time,
            'SUMMER_TARGET_END_TIME': self.summer_target_end_time,
            'SUMMER_OXPH_TARGET_MW': self.summer_oxph_target_mw,
        }


class OptimizationRun(models.Model):
    """Stores optimization run metadata and results"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    RUN_MODE_CHOICES = [
        ('forecast', 'Forecast'),
        ('historical', 'Historical Simulation'),
    ]

    OPTIMIZER_TYPE_CHOICES = [
        ('linear', 'Linear Programming'),
        ('heuristic', 'Heuristic'),
    ]

    # Basic run information
    id = models.AutoField(primary_key=True)
    run_mode = models.CharField(max_length=20, choices=RUN_MODE_CHOICES, default='forecast')
    optimizer_type = models.CharField(max_length=20, choices=OPTIMIZER_TYPE_CHOICES, default='linear')
    forecast_source = models.CharField(max_length=50, default='hydroforecast-short-term')

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    historical_start_date = models.DateField(null=True, blank=True)

    # Status and progress
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress_message = models.TextField(blank=True)
    progress_percentage = models.IntegerField(default=0)

    # Configuration
    parameter_set = models.ForeignKey(ParameterSet, on_delete=models.CASCADE, null=True, blank=True)
    custom_parameters = models.JSONField(default=dict, blank=True)  # Override specific parameters

    # Results storage
    task_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    result_file_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)

    # Summary statistics (populated after completion)
    total_spillage_af = models.FloatField(null=True, blank=True)
    avg_oxph_utilization_pct = models.FloatField(null=True, blank=True)
    peak_elevation_ft = models.FloatField(null=True, blank=True)
    min_elevation_ft = models.FloatField(null=True, blank=True)
    r_bias_cfs = models.FloatField(null=True, blank=True)

    # User tracking
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # Add diagnostics field
    solver_diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Run {self.id} - {self.get_run_mode_display()} ({self.status})"

    def get_effective_parameters(self):
        """Get the effective parameters for this run (parameter set + custom overrides)"""
        if self.parameter_set:
            params = self.parameter_set.to_dict()
        else:
            # Use default parameters if no parameter set is specified
            default_set = ParameterSet.objects.filter(is_default=True).first()
            params = default_set.to_dict() if default_set else {}

        # Apply any custom parameter overrides
        if self.custom_parameters:
            params.update(self.custom_parameters)

        return params

    def update_progress(self, message, percentage=None):
        """Update the progress of the optimization run"""
        self.progress_message = message
        if percentage is not None:
            self.progress_percentage = min(100, max(0, percentage))
        self.save(update_fields=['progress_message', 'progress_percentage'])


class OptimizationResult(models.Model):
    """Stores detailed time-series results from optimization runs"""

    optimization_run = models.ForeignKey(OptimizationRun, on_delete=models.CASCADE, related_name='results')
    timestamp_utc = models.DateTimeField()

    # Input data
    r4_flow_cfs = models.FloatField(null=True, blank=True)
    r30_flow_cfs = models.FloatField(null=True, blank=True)
    mfra_mw = models.FloatField(null=True, blank=True)
    r20_minus_r5l_cfs = models.FloatField(null=True, blank=True)
    r5l_flow_cfs = models.FloatField(null=True, blank=True)
    r26_flow_cfs = models.FloatField(null=True, blank=True)
    ccs_mode = models.IntegerField(default=0)

    # Optimization results
    oxph_generation_mw = models.FloatField(null=True, blank=True)
    abay_float_ft = models.FloatField(null=True, blank=True)
    abay_elev_ft = models.FloatField(null=True, blank=True)
    abay_af = models.FloatField(null=True, blank=True)

    # Additional diagnostic data
    mf1_2_mw = models.FloatField(null=True, blank=True)
    mf1_2_cfs = models.FloatField(null=True, blank=True)
    oxph_outflow_cfs = models.FloatField(null=True, blank=True)
    abay_delta_af = models.FloatField(null=True, blank=True)
    abay_net_flow_cfs = models.FloatField(null=True, blank=True)
    spill_volume_af = models.FloatField(null=True, blank=True)
    abay_net_expected_cfs = models.FloatField(null=True, blank=True)
    abay_net_actual_cfs = models.FloatField(null=True, blank=True)
    head_limit_mw = models.FloatField(null=True, blank=True)
    regulated_component_cfs = models.FloatField(null=True, blank=True)
    mfra_side_reduction_mw = models.FloatField(null=True, blank=True)
    bias_cfs = models.FloatField(null=True, blank=True)
    expected_abay_ft = models.FloatField(null=True, blank=True)
    expected_abay_af = models.FloatField(null=True, blank=True)
    abay_net_expected_cfs_no_bias = models.FloatField(null=True, blank=True)
    abay_net_expected_cfs_with_bias = models.FloatField(null=True, blank=True)
    is_forecast = models.BooleanField(default=False)
    raw_values = models.JSONField(default=dict, blank=True)

    # Setpoint guidance
    adjust_oxph_needed = models.CharField(max_length=20, blank=True)
    oxph_setpoint_target = models.FloatField(null=True, blank=True)
    setpoint_adjust_time_pt = models.DateTimeField(null=True, blank=True)
    is_head_loss_limited = models.BooleanField(default=False)

    # Historical comparison (for historical runs)
    actual_oxph_mw = models.FloatField(null=True, blank=True)
    actual_abay_elev_ft = models.FloatField(null=True, blank=True)
    abay_error_af = models.FloatField(null=True, blank=True)
    abay_error_cfs = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp_utc']
        unique_together = ['optimization_run', 'timestamp_utc']


class CAISODAAward(models.Model):
    """Raw per-resource, per-interval CAISO Day Ahead award records"""

    trade_date = models.DateField(help_text="CAISO market delivery date")
    interval_start_utc = models.DateTimeField(help_text="Hour start in UTC")
    interval_end_utc = models.DateTimeField(help_text="Hour end in UTC")
    resource = models.CharField(max_length=100, help_text="Resource name, e.g. MDFK_2_UNIT 1")
    mw = models.FloatField(help_text="Awarded MW")
    product_type = models.CharField(max_length=20, default='EN')
    schedule_type = models.CharField(max_length=20, default='FINAL')
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['trade_date', 'interval_start_utc', 'resource', 'product_type']]
        ordering = ['trade_date', 'interval_start_utc']

    def __str__(self):
        return f"{self.resource} {self.trade_date} {self.interval_start_utc:%H}Z {self.mw} MW"


class CAISODAAwardSummary(models.Model):
    """Pre-aggregated hourly total MW across all MFP1 energy awards"""

    trade_date = models.DateField(help_text="CAISO market delivery date")
    interval_start_utc = models.DateTimeField(help_text="Hour start in UTC")
    total_mw = models.FloatField(help_text="Sum of all MFP1 energy awards for this hour")
    resource_count = models.IntegerField(default=1, help_text="Number of resources contributing")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['trade_date', 'interval_start_utc']]
        ordering = ['trade_date', 'interval_start_utc']

    def __str__(self):
        return f"DA Summary {self.trade_date} {self.interval_start_utc:%H}Z {self.total_mw} MW"


class PIDatum(models.Model):
    """Stores historical PI data shared across all users"""

    timestamp_utc = models.DateTimeField(unique=True)
    abay_elevation_ft = models.FloatField(null=True, blank=True)
    abay_float_ft = models.FloatField(null=True, blank=True)
    oxph_generation_mw = models.FloatField(null=True, blank=True)
    oxph_setpoint_mw = models.FloatField(null=True, blank=True)
    r4_flow_cfs = models.FloatField(null=True, blank=True)
    r30_flow_cfs = models.FloatField(null=True, blank=True)
    r20_flow_cfs = models.FloatField(null=True, blank=True)
    r5l_flow_cfs = models.FloatField(null=True, blank=True)
    r26_flow_cfs = models.FloatField(null=True, blank=True)
    mfp_total_gen_mw = models.FloatField(null=True, blank=True)
    ccs_mode = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp_utc']


class UserPreferences(models.Model):
    """Store user-specific preferences and settings"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    default_parameter_set = models.ForeignKey(ParameterSet, on_delete=models.SET_NULL, null=True, blank=True)
    default_forecast_source = models.CharField(max_length=50, default='hydroforecast-short-term')
    default_optimizer_type = models.CharField(max_length=20, default='linear')

    # UI preferences
    dashboard_refresh_interval_seconds = models.IntegerField(default=300)  # 5 minutes
    show_advanced_diagnostics = models.BooleanField(default=False)
    email_notifications = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user.username}"


# django_backend/optimization_api/models.py - Updated Alert Models

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import json


# ... (keep existing UserProfile and OptimizationParameters models) ...

class UserProfile(models.Model):
    """Extended user profile for optimization parameters and preferences"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='optimization_profile')

    # User preferences
    email_notifications = models.BooleanField(default=True, help_text="Receive email notifications for alerts")
    browser_notifications = models.BooleanField(default=True, help_text="Receive browser notifications")
    alert_check_interval = models.IntegerField(default=5, help_text="Alert checking interval in minutes")
    phone_number = models.CharField(max_length=20, blank=True,
                                    help_text="Phone number for SMS alerts (format: +1234567890)")
    sms_notifications = models.BooleanField(default=False, help_text="Receive SMS notifications for critical alerts")
    refresh_interval = models.IntegerField(default=60, help_text="Dashboard refresh interval in seconds")

    # Dashboard preferences
    default_tab = models.CharField(max_length=20, default='dashboard',
                                   choices=[
                                       ('dashboard', 'Dashboard'),
                                       ('optimization', 'Optimization'),
                                       ('parameters', 'Parameters'),
                                       ('data', 'Data Table'),
                                       ('history', 'Historical Analysis'),
                                       ('prices', 'Electricity Prices'),
                                       ('rafting', 'Rafting Info')
                                   ])
    dark_mode = models.BooleanField(default=False, help_text="Use dark theme")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Add activity tracking
    last_activity = models.DateTimeField(null=True, blank=True, help_text="Last time user was active")
    last_login = models.DateTimeField(null=True, blank=True, help_text="Last login time")

    def is_online(self):
        """Check if user is currently online (active in last 10 minutes)"""
        if not self.last_activity:
            return False
        return (timezone.now() - self.last_activity).seconds < 600

    def days_since_login(self):
        """Get days since last login"""
        if not self.last_login:
            return None
        return (timezone.now() - self.last_login).days

    def __str__(self):
        return f"{self.user.username} - Optimization Profile"

    class Meta:
        verbose_name = "User Optimization Profile"
        verbose_name_plural = "User Optimization Profiles"



class OptimizationParameters(models.Model):
    """Store user's saved optimization parameters"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='optimization_parameters')

    # Parameter set identification
    name = models.CharField(max_length=100, help_text="Name for this parameter set")
    description = models.TextField(blank=True, help_text="Optional description")
    is_default = models.BooleanField(default=False, help_text="Use as default parameters")

    # Reservoir Constants
    abay_min_elev_ft = models.FloatField(
        default=1168.0,
        validators=[MinValueValidator(1160.0), MaxValueValidator(1180.0)],
        help_text="ABAY minimum elevation (ft)"
    )
    abay_max_elev_buffer_ft = models.FloatField(
        default=0.3,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text="ABAY maximum elevation buffer (ft)"
    )
    abay_elev_per_af = models.FloatField(
        default=0.0132,
        validators=[MinValueValidator(0.01), MaxValueValidator(0.02)],
        help_text="ABAY elevation per acre-foot"
    )

    # OXPH Generator Parameters
    oxph_min_mw = models.FloatField(
        default=0.8,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text="OXPH minimum MW"
    )
    oxph_max_mw = models.FloatField(
        default=5.8,
        validators=[MinValueValidator(4.0), MaxValueValidator(7.0)],
        help_text="OXPH maximum MW"
    )
    oxph_ramp_rate = models.FloatField(
        default=0.042,
        validators=[MinValueValidator(0.01), MaxValueValidator(0.1)],
        help_text="OXPH ramp rate (MW/min)"
    )

    # Linear Programming Weights
    spillage_penalty_weight = models.FloatField(
        default=10000.0,
        validators=[MinValueValidator(1000.0), MaxValueValidator(50000.0)],
        help_text="Spillage penalty weight"
    )
    summer_mw_reward_weight = models.FloatField(
        default=1000.0,
        validators=[MinValueValidator(100.0), MaxValueValidator(5000.0)],
        help_text="Summer MW reward weight"
    )
    base_smoothing_penalty = models.FloatField(
        default=100.0,
        validators=[MinValueValidator(10.0), MaxValueValidator(1000.0)],
        help_text="Base smoothing penalty"
    )

    # Summer Schedule Parameters
    summer_target_start_time = models.TimeField(default='08:00', help_text="Summer target start time")
    summer_oxph_target_mw = models.FloatField(
        default=5.8,
        validators=[MinValueValidator(4.0), MaxValueValidator(6.0)],
        help_text="Summer OXPH target MW"
    )

    # Water Year Type
    WATER_YEAR_CHOICES = [
        ('Wet', 'Wet'),
        ('Above Normal', 'Above Normal'),
        ('Below Normal', 'Below Normal'),
        ('Dry', 'Dry'),
        ('Critical', 'Critical'),
        ('Extreme Critical', 'Extreme Critical'),
    ]
    water_year_type = models.CharField(
        max_length=20,
        choices=WATER_YEAR_CHOICES,
        default='Below Normal',
        help_text="Current water year classification"
    )

    # Rafting Schedule Parameters
    rafting_season_end_date = models.DateField(default='2025-09-30', help_text="End of rafting season")
    oxph_target_mw_rafting = models.FloatField(
        default=5.8,
        validators=[MinValueValidator(4.0), MaxValueValidator(6.0)],
        help_text="OXPH target MW during rafting"
    )
    early_release_dates = models.TextField(
        blank=True,
        help_text="Early release Saturday dates (YYYY-MM-DD, one per line)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    def get_early_release_dates_list(self):
        """Convert early release dates text to list"""
        if not self.early_release_dates:
            return []
        return [date.strip() for date in self.early_release_dates.split('\n') if date.strip()]

    def to_dict(self):
        """Convert parameters to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'is_default': self.is_default,
            'abay_min_elev_ft': self.abay_min_elev_ft,
            'abay_max_elev_buffer_ft': self.abay_max_elev_buffer_ft,
            'abay_elev_per_af': self.abay_elev_per_af,
            'oxph_min_mw': self.oxph_min_mw,
            'oxph_max_mw': self.oxph_max_mw,
            'oxph_ramp_rate': self.oxph_ramp_rate,
            'spillage_penalty_weight': self.spillage_penalty_weight,
            'summer_mw_reward_weight': self.summer_mw_reward_weight,
            'base_smoothing_penalty': self.base_smoothing_penalty,
            'summer_target_start_time': self.summer_target_start_time.strftime('%H:%M'),
            'summer_oxph_target_mw': self.summer_oxph_target_mw,
            'water_year_type': self.water_year_type,
            'rafting_season_end_date': self.rafting_season_end_date.isoformat(),
            'oxph_target_mw_rafting': self.oxph_target_mw_rafting,
            'early_release_dates': self.get_early_release_dates_list(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    class Meta:
        verbose_name = "Optimization Parameters"
        verbose_name_plural = "Optimization Parameters"
        unique_together = [['user', 'name']]


class AlertThreshold(models.Model):
    """User-defined alert thresholds for monitoring"""


    CONDITION_CHOICES = [
        ('greater_than', 'Greater Than'),
        ('less_than', 'Less Than'),
        ('equal_to', 'Equal To'),
        ('between', 'Between'),
        ('outside_range', 'Outside Range'),
    ]

    PARAMETER_CHOICES = [
        ('afterbay_elevation', 'Afterbay Elevation (ft)'),
        ('oxph_power', 'OXPH Power (MW)'),
        ('r4_flow', 'R4 Flow (CFS)'),
        ('r30_flow', 'R30 Flow (CFS)'),
        ('mfra_power', 'MFRA Power (MW)'),
        ('float_level', 'Float Level (ft)'),
        ('net_flow', 'Net Flow (CFS)'),
        ('spillage', 'Spillage (AF)'),
    ]

    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    # Add new fields for enhanced alert system
    CATEGORY_CHOICES = [
        ('flow', 'Flow Alerts'),
        ('afterbay', 'Afterbay Alerts'),
        ('rafting', 'Rafting Alerts'),
        ('generation', 'Generation Alerts'),
        ('general', 'General Alerts'),
    ]

    SPECIAL_TYPE_CHOICES = [
        ('standard', 'Standard Alert'),
        ('rafting_ramp', 'Rafting Ramp Alert'),
        ('float_change', 'Float Level Change'),
        ('deviation', 'Deviation Alert'),
    ]

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='general',
        help_text="Alert category for grouping"
    )

    special_type = models.CharField(
        max_length=20,
        choices=SPECIAL_TYPE_CHOICES,
        default='standard',
        help_text="Special alert type requiring custom logic"
    )

    # Metadata field for storing additional configuration
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional configuration for special alert types"
    )

    # For tracking float level changes
    last_known_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Last known value for change detection"
    )

    # Add methods for special alert checking
    # def check_rafting_ramp_condition(self, current_time, current_oxph_mw):
    #     """Check if OXPH needs to be ramped for rafting schedule"""
    #     if self.special_type != 'rafting_ramp':
    #         return False
    #
    #     metadata = self.metadata or {}
    #     start_time = metadata.get('start_time')
    #     ramp_up_buffer = metadata.get('ramp_up_buffer', 90)  # minutes
    #
    #     if not start_time:
    #         return False
    #
    #     # Calculate when ramp should start based on current OXPH and target
    #     from datetime import datetime, timedelta
    #     from django.utils import timezone
    #
    #     # Parse rafting start time
    #     today = timezone.now().date()
    #     rafting_start = datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
    #     rafting_start = timezone.make_aware(rafting_start)
    #
    #     # Calculate required ramp time
    #     target_mw = self.threshold_value  # 5.8 MW for rafting
    #     ramp_rate = 0.042  # MW per minute (from your constants)
    #     mw_to_ramp = target_mw - current_oxph_mw
    #
    #     if mw_to_ramp <= 0:
    #         return False  # Already at or above target
    #
    #     ramp_time_needed = mw_to_ramp / ramp_rate  # minutes
    #
    #     # When should ramp start?
    #     ramp_start_time = rafting_start - timedelta(minutes=ramp_time_needed)
    #     alert_time = ramp_start_time - timedelta(minutes=ramp_up_buffer)
    #
    #     # Check if we're within the alert window
    #     now = timezone.now()
    #     if alert_time <= now <= ramp_start_time:
    #         return not self.is_in_cooldown()
    #
    #     return False
    #
    # def check_float_change_condition(self, current_value):
    #     """Check if float level has changed significantly"""
    #     if self.special_type != 'float_change':
    #         return False
    #
    #     if self.last_known_value is None:
    #         # First time checking, just store the value
    #         self.last_known_value = current_value
    #         self.save(update_fields=['last_known_value'])
    #         return False
    #
    #     # Check if change exceeds threshold
    #     change = abs(current_value - self.last_known_value)
    #     if change >= self.threshold_value:  # threshold_value is sensitivity
    #         self.last_known_value = current_value
    #         self.save(update_fields=['last_known_value'])
    #         return not self.is_in_cooldown()
    #
    #     return False
    #
    # def check_deviation_condition(self, current_value, setpoint):
    #     """Check if value deviates from setpoint by more than threshold"""
    #     if self.special_type != 'deviation':
    #         return False
    #
    #     deviation = abs(current_value - setpoint)
    #     return deviation > self.threshold_value and not self.is_in_cooldown()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alert_thresholds')

    sms_notification = models.BooleanField(default=False, help_text="Send SMS notifications")
    voice_notification = models.BooleanField(default=False, help_text="Make voice calls for critical alerts")

    # Alert definition
    name = models.CharField(max_length=100, help_text="Name for this alert")
    description = models.TextField(blank=True, help_text="Optional description")
    parameter = models.CharField(max_length=30, choices=PARAMETER_CHOICES, help_text="Parameter to monitor")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, help_text="Alert condition")

    # Threshold values
    threshold_value = models.FloatField(help_text="Primary threshold value")
    threshold_value_max = models.FloatField(null=True, blank=True, help_text="Maximum value for range conditions")

    # Alert settings
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='warning')
    is_active = models.BooleanField(default=True, help_text="Enable this alert")
    email_notification = models.BooleanField(default=True, help_text="Send email notifications")
    browser_notification = models.BooleanField(default=True, help_text="Show browser notifications")

    # Cooldown to prevent spam
    cooldown_minutes = models.IntegerField(default=30, help_text="Minutes to wait before re-alerting")
    last_triggered = models.DateTimeField(null=True, blank=True, help_text="Last time this alert was triggered")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.name} ({self.parameter})"

    def check_condition(self, value):
        """Check if the given value triggers this alert"""
        if not self.is_active:
            return False

        try:
            value = float(value)

            if self.condition == 'greater_than':
                return value > self.threshold_value
            elif self.condition == 'less_than':
                return value < self.threshold_value
            elif self.condition == 'equal_to':
                return abs(value - self.threshold_value) < 0.01  # Small tolerance for floats
            elif self.condition == 'between':
                return self.threshold_value <= value <= (self.threshold_value_max or self.threshold_value)
            elif self.condition == 'outside_range':
                return value < self.threshold_value or value > (self.threshold_value_max or self.threshold_value)

        except (ValueError, TypeError):
            return False

        return False


    def is_in_cooldown(self):
        """Check if alert is in cooldown period"""
        if not self.last_triggered:
            return False

        from django.utils import timezone
        cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
        return timezone.now() < cooldown_end

    def to_dict(self):
        """Convert alert to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'parameter': self.parameter,
            'condition': self.condition,
            'threshold_value': self.threshold_value,
            'threshold_value_max': self.threshold_value_max,
            'severity': self.severity,
            'is_active': self.is_active,
            'email_notification': self.email_notification,
            'browser_notification': self.browser_notification,
            'cooldown_minutes': self.cooldown_minutes,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    class Meta:
        verbose_name = "Alert Threshold"
        verbose_name_plural = "Alert Thresholds"
        unique_together = [['user', 'name']]


class AlertLog(models.Model):
    """Log of triggered alerts"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alert_logs')
    alert_threshold = models.ForeignKey(AlertThreshold, on_delete=models.CASCADE, related_name='logs')

    sms_sent = models.BooleanField(default=False)
    voice_sent = models.BooleanField(default=False)

    # Alert details
    triggered_value = models.FloatField(help_text="Value that triggered the alert")
    message = models.TextField(help_text="Alert message")
    severity = models.CharField(max_length=10, help_text="Alert severity at time of trigger")

    # Notification status
    email_sent = models.BooleanField(default=False)
    browser_shown = models.BooleanField(default=False)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.alert_threshold.name} @ {self.created_at}"

    def to_dict(self):
        """Convert alert log to dictionary for API responses"""
        return {
            'id': self.id,
            'alert_name': self.alert_threshold.name,
            'parameter': self.alert_threshold.parameter,
            'triggered_value': self.triggered_value,
            'message': self.message,
            'severity': self.severity,
            'email_sent': self.email_sent,
            'browser_shown': self.browser_shown,
            'acknowledged': self.acknowledged,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'created_at': self.created_at.isoformat()
        }

    class Meta:
        verbose_name = "Alert Log"
        verbose_name_plural = "Alert Logs"
        ordering = ['-created_at']

# Additional model for tracking system availability
class SystemStatus(models.Model):
    """Track system status and data availability"""

    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('degraded', 'Degraded'),
        ('maintenance', 'Maintenance'),
    ]

    alerts_triggered_count = models.IntegerField(default=0, help_text="Number of alerts triggered in this check")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='online')
    pi_data_available = models.BooleanField(default=True)
    last_pi_update = models.DateTimeField(null=True, blank=True)
    optimization_available = models.BooleanField(default=True)
    alert_system_active = models.BooleanField(default=True)

    # System metrics
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)
    disk_usage = models.FloatField(null=True, blank=True)

    # Notes
    status_message = models.TextField(blank=True)

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"System Status - {self.status} @ {self.created_at}"

    class Meta:
        verbose_name = "System Status"
        verbose_name_plural = "System Status History"
        ordering = ['-created_at']


# Add this new model for tracking rafting schedules
class RaftingSchedule(models.Model):
    """Track rafting schedules for alerts"""

    date = models.DateField(help_text="Date of rafting schedule")
    start_time = models.TimeField(help_text="Rafting start time")
    end_time = models.TimeField(help_text="Rafting end time")
    is_early_release = models.BooleanField(default=False)

    # OXPH requirements
    target_mw = models.FloatField(default=5.8, help_text="Target OXPH MW for rafting")
    ramp_up_minutes = models.IntegerField(default=90, help_text="Minutes needed to ramp up")
    ramp_down_minutes = models.IntegerField(default=30, help_text="Minutes needed to ramp down")

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['date', 'created_by']]
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"Rafting on {self.date} from {self.start_time} to {self.end_time}"



# Signal to create user profile when user is created
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'optimization_profile'):
        instance.optimization_profile.save()




