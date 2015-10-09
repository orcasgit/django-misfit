import django
import random

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase
from misfit import Misfit, MisfitProfile
from mock import patch, Mock

from misfitapp.models import MisfitUser

try:
    from urllib.parse import urlencode
    from string import ascii_letters
except:  # Python 2.x
    from urllib import urlencode
    from string import letters as ascii_letters


class MisfitTestBase(TestCase):
    TEST_SERVER = 'http://testserver'

    def setUp(self):
        self.username = self.random_string(25)
        self.password = self.random_string(25)
        self.user = self.create_user(username=self.username,
                                     password=self.password)
        self.misfit_user_id = '51a4189acf12e53f79000001'
        self.access_token = self.random_string(25)
        self.misfit_user = self.create_misfit_user(user=self.user)
        self.profile = MisfitProfile({
            'userId': self.misfit_user_id,
            'birthday': '1368-09-22',
            'name': 'Frodo Baggins',
            'gender': 'male',
            'email': 'theringbearer@example.com'
        })

        self.client.login(username=self.username, password=self.password)

    def random_string(self, length=255, extra_chars=''):
        chars = ascii_letters + extra_chars
        return ''.join([random.choice(chars) for i in range(length)])

    def create_user(self, username=None, email=None, password=None, **kwargs):
        username = username or self.random_string(25)
        email = email or '{0}@{1}.com'.format(self.random_string(25),
                                              self.random_string(10))
        password = password or self.random_string(25)
        user = User.objects.create_user(username, email, password)
        User.objects.filter(pk=user.pk).update(**kwargs)
        user = User.objects.get(pk=user.pk)
        return user

    def create_misfit_user(self, **kwargs):
        defaults = {
            'user': kwargs.pop('user', self.create_user()),
            'misfit_user_id': self.misfit_user_id,
            'access_token': self.access_token
        }
        defaults.update(kwargs)
        return MisfitUser.objects.create(**defaults)

    def assertRedirectsNoFollow(self, response, url, status_code=302):
        """
        Workaround to test whether a response redirects to another URL without
        loading the page at that URL.
        """
        self.assertEqual(response.status_code, status_code)
        if django.VERSION < (1,9):
            url = self.TEST_SERVER + url
        self.assertEqual(response._headers['location'][1], url)

    def _get(self, url_name=None, url_kwargs=None, get_kwargs=None, **kwargs):
        """Convenience wrapper for test client GET request."""
        url_name = url_name or self.url_name
        url = reverse(url_name, kwargs=url_kwargs)  # Base URL.

        # Add GET parameters.
        if get_kwargs:
            url += '?' + urlencode(get_kwargs)

        return self.client.get(url, **kwargs)

    def _set_session_vars(self, **kwargs):
        session = self.client.session
        for key, value in kwargs.items():
            session[key] = value
        try:
            session.save()  # Only available on authenticated sessions.
        except AttributeError:
            pass

    def _error_response(self):
        error_response = Mock(['content'])
        error_response.content = '{"errors": []}'.encode('utf8')
        return error_response
