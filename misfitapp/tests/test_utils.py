from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from misfit import Misfit

from misfitapp.utils import create_misfit, get_setting


class TestMisfitUtilities(TestCase):
    def test_create_misfit(self):
        """
        Check that the create_misfit utility creates a Misfit object
        and an error is raised when the client id or secret aren't set.
        """
        with self.settings(MISFIT_CLIENT_ID=None, MISFIT_CLIENT_SECRET=None):
            self.assertRaises(ImproperlyConfigured, create_misfit, 'token')
        with self.settings(MISFIT_CLIENT_ID='', MISFIT_CLIENT_SECRET=None):
            self.assertRaises(ImproperlyConfigured, create_misfit, 'token')
        with self.settings(MISFIT_CLIENT_ID=None, MISFIT_CLIENT_SECRET=''):
            self.assertRaises(ImproperlyConfigured, create_misfit, 'token')
        api = create_misfit('token')
        self.assertEqual(api.__class__, Misfit)

    def test_get_setting_error(self):
        """
        Check that an error is raised when trying to get a nonexistent setting.
        """
        self.assertRaises(ImproperlyConfigured, get_setting, 'DOES_NOT_EXIST')
