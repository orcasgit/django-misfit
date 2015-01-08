from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from misfit import Misfit
from misfit.auth import MisfitAuth
from misfit.exceptions import MisfitRateLimitError
from mock import patch

from misfitapp import utils
from misfitapp.decorators import misfit_integration_warning
from misfitapp.models import MisfitUser

from .base import MisfitTestBase

try:
    from unittest import mock
except ImportError:  # Python 2.x fallback
    import mock


class TestIntegrationUtility(MisfitTestBase):

    def test_is_integrated(self):
        """Users with stored OAuth information are integrated."""
        self.assertTrue(utils.is_integrated(self.user))

    def test_is_not_integrated(self):
        """User is not integrated if we have no OAuth data for them."""
        MisfitUser.objects.all().delete()
        self.assertFalse(utils.is_integrated(self.user))

    def test_unauthenticated(self):
        """User is not integrated if they aren't logged in."""
        user = AnonymousUser()
        self.assertFalse(utils.is_integrated(user))


class TestIntegrationDecorator(MisfitTestBase):

    def setUp(self):
        super(TestIntegrationDecorator, self).setUp()
        self.fake_request = HttpRequest()
        self.fake_request.user = self.user
        self.fake_view = lambda request: "hello"
        self.messages = []

    def _mock_decorator(self, msg=None):
        def mock_error(request, message, *args, **kwargs):
            self.messages.append(message)

        with mock.patch.object(messages, 'error', mock_error) as error:
            return misfit_integration_warning(msg=msg)(self.fake_view)(
                self.fake_request)

    def test_unauthenticated(self):
        """Message should be added if user is not logged in."""
        self.fake_request.user = AnonymousUser()
        results = self._mock_decorator()

        self.assertEqual(results, "hello")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0],
                utils.get_setting('MISFIT_DECORATOR_MESSAGE'))

    def test_is_integrated(self):
        """Decorator should have no effect if user is integrated."""
        results = self._mock_decorator()

        self.assertEqual(results, "hello")
        self.assertEqual(len(self.messages), 0)

    def test_is_not_integrated(self):
        """Message should be added if user is not integrated."""
        MisfitUser.objects.all().delete()
        results = self._mock_decorator()

        self.assertEqual(results, "hello")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0],
                utils.get_setting('MISFIT_DECORATOR_MESSAGE'))

    def test_custom_msg(self):
        """Decorator should support a custom message string."""
        MisfitUser.objects.all().delete()
        msg = "customized"
        results = self._mock_decorator(msg)

        self.assertEqual(results, "hello")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0], "customized")

    def test_custom_msg_func(self):
        """Decorator should support a custom message function."""
        MisfitUser.objects.all().delete()
        msg = lambda request: "message to {0}".format(request.user)
        results = self._mock_decorator(msg)

        self.assertEqual(results, "hello")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0], msg(self.fake_request))


class TestLoginView(MisfitTestBase):
    url_name = 'misfit-login'

    def setUp(self):
        super(TestLoginView, self).setUp()
        MisfitAuth.authorize_url = mock.MagicMock(return_value='/test')

    def test_get(self):
        """
        Login view should generate & store a request token then
        redirect to an authorization URL.
        """
        response = self._get()
        self.assertRedirectsNoFollow(response, '/test')
        self.assertTrue('state' in self.client.session)
        self.assertEqual(MisfitUser.objects.count(), 1)

    def test_unauthenticated(self):
        """User must be logged in to access Login view."""
        self.client.logout()
        response = self._get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MisfitUser.objects.count(), 1)

    def test_unintegrated(self):
        """Misfit credentials not required to access Login view."""
        self.misfit_user.delete()
        response = self._get()
        self.assertRedirectsNoFollow(response, '/test')
        self.assertTrue('state' in self.client.session)
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_next(self):
        response = self._get(get_kwargs={'next': '/next'})
        self.assertRedirectsNoFollow(response, '/test')
        self.assertEqual(
            self.client.session.get('misfit_next', None), '/next')
        self.assertEqual(MisfitUser.objects.count(), 1)


class TestCompleteView(MisfitTestBase):
    url_name = 'misfit-complete'
    state = 'fake-state'

    def setUp(self):
        super(TestCompleteView, self).setUp()
        self.misfit_user.delete()

    def _get(self, use_token=True, use_verifier=True, use_limiting=False, **kwargs):
        MisfitAuth.fetch_token = mock.MagicMock(return_value=self.access_token)
        Misfit.profile = mock.MagicMock(return_value=self.profile)
        if use_limiting:
            Misfit.profile.side_effect = MisfitRateLimitError(429, 'Ooopsy.')
        if use_token:
            self._set_session_vars(state=self.state)
        get_kwargs = kwargs.pop('get_kwargs', {})
        if use_verifier:
            get_kwargs.update({'code': 'verifier',
                               'state': self.state})
        return super(TestCompleteView, self)._get(get_kwargs=get_kwargs,
                                                  **kwargs)

    def test_error_redirect(self):
        """  Complete view should redirect to MISFIT_ERROR_REDIRECT if set. """
        url = '/'
        with patch('celery.app.task.Task.delay') as mock_delay:
            with self.settings(MISFIT_ERROR_REDIRECT=url):
                response = self._get(use_limiting=True)
        self.assertRedirectsNoFollow(response, url)


    def test_ratelimiting(self):
        with patch('celery.app.task.Task.delay') as mock_delay:
            response = self._get(use_limiting=True)
            self.assertRedirectsNoFollow(response, reverse('misfit-error'))


    def test_get(self):
        """
        Complete view should fetch & store the user's access token and add
        the user's profile to the session
        """
        with patch('celery.app.task.Task.delay') as mock_delay:
            response = self._get()
        self.assertRedirectsNoFollow(
            response, utils.get_setting('MISFIT_LOGIN_REDIRECT'))
        misfit_user = MisfitUser.objects.get()
        self.assertEqual(Misfit.profile.call_count, 1)
        Misfit.profile.assert_called_once_with()
        self.assertEqual(misfit_user.user, self.user)
        self.assertEqual(misfit_user.access_token, self.access_token)
        self.assertEqual(misfit_user.misfit_user_id, self.misfit_user_id)

    def test_unauthenticated(self):
        """User must be logged in to access Complete view."""
        self.client.logout()
        response = self._get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_next(self):
        """
        Complete view should redirect to session['misfit_next'] if available.
        """
        self._set_session_vars(misfit_next='/test')
        with patch('celery.app.task.Task.delay') as mock_delay:
            response = self._get()
        self.assertRedirectsNoFollow(response, '/test')
        misfit_user = MisfitUser.objects.get()
        self.assertEqual(misfit_user.user, self.user)
        self.assertEqual(misfit_user.access_token, self.access_token)
        self.assertEqual(misfit_user.misfit_user_id, self.misfit_user_id)

    def test_no_token(self):
        """Complete view should redirect to error if token isn't in session."""
        response = self._get(use_token=False)
        self.assertRedirectsNoFollow(response, reverse('misfit-error'))
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_no_verifier(self):
        """
        Complete view should redirect to error if verifier param is not
        present.
        """
        response = self._get(use_verifier=False)
        self.assertRedirectsNoFollow(response, reverse('misfit-error'))
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_integrated(self):
        """
        Complete view should overwrite existing credentials for this user.
        """
        self.misfit_user = self.create_misfit_user(user=self.user)
        with patch('celery.app.task.Task.delay') as mock_delay:
            response = self._get()
        misfit_user = MisfitUser.objects.get()
        self.assertEqual(misfit_user.user, self.user)
        self.assertEqual(misfit_user.access_token, self.access_token)
        self.assertEqual(misfit_user.misfit_user_id, self.misfit_user_id)
        self.assertRedirectsNoFollow(
            response, utils.get_setting('MISFIT_LOGIN_REDIRECT'))


class TestErrorView(MisfitTestBase):
    url_name = 'misfit-error'

    def test_get(self):
        """Should be able to retrieve Error page."""
        response = self._get()
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated(self):
        """User must be logged in to access Error view."""
        self.client.logout()
        response = self._get()
        self.assertEqual(response.status_code, 302)

    def test_unintegrated(self):
        """No Misfit credentials required to access Error view."""
        self.misfit_user.delete()
        response = self._get()
        self.assertEqual(response.status_code, 200)


class TestLogoutView(MisfitTestBase):
    url_name = 'misfit-logout'

    def setUp(self):
        super(TestLogoutView, self).setUp()

    def test_get(self):
        """Logout view should remove associated MisfitUser and redirect."""
        response = self._get()
        self.assertRedirectsNoFollow(response,
            utils.get_setting('MISFIT_LOGIN_REDIRECT'))
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_unauthenticated(self):
        """User must be logged in to access Logout view."""
        self.client.logout()
        response = self._get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MisfitUser.objects.count(), 1)

    def test_unintegrated(self):
        """No Misfit credentials required to access Logout view."""
        self.misfit_user.delete()
        response = self._get()
        self.assertRedirectsNoFollow(response,
            utils.get_setting('MISFIT_LOGIN_REDIRECT'))
        self.assertEqual(MisfitUser.objects.count(), 0)

    def test_next(self):
        """Logout view should redirect to GET['next'] if available."""
        response = self._get(get_kwargs={'next': '/test'})
        self.assertRedirectsNoFollow(response, '/test')
        self.assertEqual(MisfitUser.objects.count(), 0)
