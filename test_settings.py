import os

from datetime import datetime


PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'django_misfit',
    }
}
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'misfitapp',
]
SECRET_KEY = 'something-secret'
ROOT_URLCONF = 'misfitapp.urls'

USE_TZ = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': [
            os.path.join(PROJECT_PATH, 'misfitapp', 'templates'),
            os.path.join(PROJECT_PATH, 'misfitapp', 'tests', 'templates')
        ],
    },
]

MISFIT_CLIENT_ID = 'FAKE_ID'
MISFIT_CLIENT_SECRET = 'FAKE_SECRET'
MISFIT_HISTORIC_TIMEDELTA = datetime.now() - datetime(2014, 1, 1)

LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler'
        },
    },
    'loggers': {
        'misfitapp.tasks': {'handlers': ['console'], 'level': 'DEBUG'},
    },
}

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
)
