#!/usr/bin/env python

import coverage
import datetime
import optparse
import os
import sys

from django.conf import settings

PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))

if not settings.configured:
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': 'django_misfit',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.messages',
            'django.contrib.sessions',
            'misfitapp',
        ],
        SECRET_KEY='something-secret',
        ROOT_URLCONF='misfitapp.urls',

        USE_TZ = True,

        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'DIRS': [
                    os.path.join(PROJECT_PATH, 'misfitapp', 'templates'),
                    os.path.join(PROJECT_PATH, 'misfitapp', 'tests', 'templates')
                ],
            },
        ],

        MISFIT_CLIENT_ID='FAKE_ID',
        MISFIT_CLIENT_SECRET='FAKE_SECRET',
        MISFIT_HISTORIC_TIMEDELTA=datetime.datetime.now() - datetime.datetime(2014, 1, 1),

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
        },

        MIDDLEWARE_CLASSES = (
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
        )
    )


from django.test.utils import get_runner


def run_tests():
    parser = optparse.OptionParser()
    parser.add_option('--coverage', dest='coverage', default='2',
                      help="coverage level, 0=no coverage, 1=without branches,"
                      " 2=with branches")
    options, tests = parser.parse_args()
    tests = tests or ['misfitapp']

    covlevel = int(options.coverage)
    if covlevel:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if covlevel == 2:
            branch = True
        else:
            branch = False
        cov = coverage.coverage(branch=branch, config_file='.coveragerc')
        cov.load()
        cov.start()

    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=1, interactive=True, failfast=False)
    exit_val = test_runner.run_tests(tests)

    if covlevel:
        cov.stop()
        cov.save()

    sys.exit(exit_val)


import django
# In Django >= 1.7, we need to run setup first
if hasattr(django, 'setup'):
    django.setup()


if __name__ == '__main__':
    run_tests()
