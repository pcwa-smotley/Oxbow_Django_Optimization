# django_backend/abay_web/settings.py

import mimetypes
import os
from pathlib import Path
import configparser

mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-your-secret-key-here-change-in-production'

#*********
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
CELERY_TASK_ALWAYS_EAGER = False        # CHANGE To False in production
#CELERY_TASK_EAGER_PROPAGATES = True     # CHANGE To False in production
#***********************************************************************


# Disable signup/registration in any third-party apps
ACCOUNT_SIGNUP_ENABLED = False  # If using django-allauth

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'optimization_api',
    'django_celery_beat',
    'django_celery_results',
]



MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'optimization_api.middleware.UpdateLastActivityMiddleware'
]

ROOT_URLCONF = 'django_backend.urls'

WSGI_APPLICATION = 'django_backend.wsgi.application'
ASGI_APPLICATION = 'django_backend.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# Celery Configuration (if not already present)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'America/Los_Angeles'

if os.name == "nt":
    CELERY_WORKER_POOL = "solo"

# Alert System Configuration
ALERT_SYSTEM = {
    'DEFAULT_COOLDOWN_MINUTES': 30,
    'MAX_ALERTS_PER_USER': 50,
    'ALERT_LOG_RETENTION_DAYS': 30,
    'ENABLE_VOICE_CALLS': True,
    'VOICE_CALL_SEVERITY': ['critical'],
}

# Login/Logout URLs
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            # Increase timeout to 20 seconds to handle occasional locks
            'timeout': 20,
            # Note: init_command removed for compatibility with newer Python versions
            # PRAGMA settings are now handled via Django signals (see below)
        }
    }
}

# SQLite optimizations are now handled in optimization_api/apps.py to avoid import issues
# The PRAGMA commands for WAL mode and other optimizations are set when the database connection is created

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Los_Angeles'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Static files finders
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',  # Change in production
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100
}

# CORS settings (for local development)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",  # If you use a separate frontend server
]

CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only for development

# Celery Configuration (for background tasks)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# Channels (WebSocket) configuration
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}

# Custom settings for ABAY optimization
ABAY_OPTIMIZATION = {
    'OUTPUT_DIR': BASE_DIR / 'optimization_outputs',
    'MAX_CONCURRENT_OPTIMIZATIONS': 3,
    'OPTIMIZATION_TIMEOUT_SECONDS': 300,  # 5 minutes

    'USE_SIMULATED_DATA': False,  # Set to True to use simulated data instead of real optimization

    'YES_ENERGY': {
        'ENABLED': True,  # Set to False to use simulated data only
        'DEFAULT_NODE_ID': '20000002064',  # CAISO SP15 node
        'CACHE_TIMEOUT_SECONDS': 300,  # Cache price data for 5 minutes
        'MAX_RETRIES': 3,
        'RETRY_DELAY_SECONDS': 5,
    }
}

# Add caching for price data (optional but recommended)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'abay-optimization-cache',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'database': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        # Add a separate handler for SQLite issues
        'sqlite_file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'sqlite_locks.log',
            'formatter': 'database',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'optimization_api': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'abay_opt': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Add SQLite backend logging
        'django.db.backends': {
            'handlers': ['sqlite_file'],
            'level': 'WARNING',  # Will catch lock timeouts and errors
            'propagate': False,
        },
        # Optional: More detailed SQL logging (only enable if debugging)
        # 'django.db.backends.sqlite3': {
        #     'handlers': ['sqlite_file'],
        #     'level': 'DEBUG',  # Shows all SQL queries
        #     'propagate': False,
        # },
    },
}

# Site URL for email links
SITE_URL = 'http://localhost:8000'  # Update for production

# Get the correct path cor config file
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
config_path = PROJECT_ROOT / 'abay_opt' / 'config'

# Load config
config = configparser.ConfigParser()
if config_path.exists():
    config.read(config_path)

else:
    print(f"Config file not found at: {config_path}")


# Email configuration for alerts
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config.get("EMAIL", "smtp_server", fallback='smtp.gmail.com') # Or your SMTP server
EMAIL_PORT = config.get("EMAIL", "smtp_port", fallback=465)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config.get("EMAIL", "username", fallback=None)
EMAIL_HOST_PASSWORD = config.get("EMAIL", "password", fallback=None)
DEFAULT_FROM_EMAIL = 'ABAY Alerts <pcwa.weather@gmail.com>'

# Twilio Configuration for SMS and Voice Alerts
TWILIO_ACCOUNT_SID = config.get("TWILIO", "account_sid", fallback=None)
TWILIO_AUTH_TOKEN = config.get("TWILIO", "auth_token", fallback=None)
TWILIO_PHONE_NUMBER = config.get("TWILIO", "phone_number", fallback=None)  # Your Twilio phone number

# Session configuration for "Remember Me"
SESSION_COOKIE_NAME = 'abay_sessionid'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days
SESSION_SAVE_EVERY_REQUEST = False  # Important: Don't reset on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Allow persistent sessions

# Security settings
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF token should match session length
CSRF_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days






