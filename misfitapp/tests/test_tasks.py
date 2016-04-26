from __future__ import absolute_import

import arrow
import celery
import datetime
import json
import sys

from celery import Celery
from celery.exceptions import Reject
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from freezegun import freeze_time
from httmock import HTTMock, urlmatch
from misfit import exceptions as misfit_exceptions
from misfit import Misfit
from misfit.notification import MisfitMessage
from mock import call, MagicMock, patch
from nose.tools import eq_
from six.moves import urllib

from misfitapp import utils
from misfitapp.models import (
    MisfitUser,
    Device,
    Goal,
    Profile,
    Session,
    Sleep,
    SleepSegment,
    Summary
)
from misfitapp.tasks import (
    process_notification,
    import_historical,
    import_historical_cls,
    )

try:
    from io import BytesIO
except ImportError:  # Python 2.x fallback
    from StringIO import StringIO as BytesIO

from .base import MisfitTestBase


@urlmatch(scheme='https', netloc='example-subscribe-url.com')
def sns_subscribe(*args):
    """ Mock requests to the SNS SubscribeURL """
    return ''


class JsonMock:
    def __init__(self, file_name_base=None, date_range=None):
        """ Build the response template """
        self.headers = {'content-type': 'application/json; charset=utf-8'}
        self.response_tmpl = {'status_code': 200, 'headers': self.headers}
        self.file_name_base = file_name_base
        self.date_range = date_range

    def json_file(self):
        response = self.response_tmpl
        file_path = 'misfitapp/tests/responses/%s.json' % self.file_name_base
        with open(file_path) as json_file:
            response['content'] = json_file.read().encode('utf8')
        return response

    def add_start_date_to_id(self, objects, url):
        """
        Append the start date of the request to the ID, ensuring it will be
        unique
        """
        response = self.json_file()
        qs_dict = urllib.parse.parse_qs(url.query)
        if 'start_date' in qs_dict:
            start_date = qs_dict['start_date'][0]
            content = json.loads(response['content'].decode('utf8'))
            for i in range(len(content[objects])):
                content[objects][i]['id'] += start_date
            response['content'] = json.dumps(content).encode('utf8')
        return response

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/device/.*')
    def device_http(self, url, *args):
        """ Method to return the contents of a device json file """
        self.file_name_base = 'device'
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/goals/.*')
    def goal_http(self, url, *args):
        """ Method to return the contents of a goal json file """
        if not self.file_name_base:
            self.file_name_base = 'goal_' + url.path.split('/')[-2]
            response = self.json_file()
            # Reset file_name_base for future requests
            self.file_name_base = None
        else:
            response = self.add_start_date_to_id('goals', url)
        return response

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/sessions/.*')
    def session_http(self, url, *args):
        """ Method to return the contents of a session json file """
        if not self.file_name_base:
            self.file_name_base = 'session_' + url.path.split('/')[-2]
        return self.add_start_date_to_id('sessions', url)

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/.*/profile/*')
    def profile_http(self, url, *args):
        """ Method to return the contents of a profile json file """
        self.file_name_base = 'profile'
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/sleeps/.*')
    def sleep_http(self, url, *args):
        """ Method to return the contents of a sleep json file """
        if not self.file_name_base:
            self.file_name_base = 'sleep_' + url.path.split('/')[-2]
        if self.date_range:
            # If a date range was specified, only return data when the query
            # contains the specified range
            if (url.query.find('start_date=%s' % self.date_range[0]) > -1 and
                    url.query.find('end_date=%s' % self.date_range[1]) > -1):
                return self.json_file()
            else:
                response = self.response_tmpl
                response['content'] = '{"sleeps": []}'.encode('utf8')
                return response
        else:
            return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/summary/.*')
    def summary_http(self, *args):
        """ Generic method to return the contents of a summary file """
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com')
    def json_http(self, *args):
        """ Generic method to return the contents of a json file """
        return self.json_file()


class TestImportHistoricalTask(MisfitTestBase):

    def setUp(self):
        super(TestImportHistoricalTask, self).setUp()

    @patch('misfitapp.models.chunkify_dates')
    @patch('misfit.notification.MisfitNotification.verify_signature')
    def test_import_historical(self, verify_signature_mock, chunkify_dates_mock):
        chunkify_dates_mock.return_value = [
            (datetime.date(2014, 1, 1), datetime.date(2014, 1, 31)),
            (datetime.date(2014, 1, 31), datetime.date(2014, 3, 2)),
            (datetime.date(2014, 3, 2), datetime.date(2014, 4, 1)),
            (datetime.date(2014, 4, 1), datetime.date(2014, 5, 1)),
            (datetime.date(2014, 5, 1), datetime.date(2014, 5, 31)),
        ]
        eq_(Profile.objects.filter(user=self.user).count(), 0)
        eq_(Device.objects.filter(user=self.user).count(), 0)
        eq_(Goal.objects.filter(user=self.user).count(), 0)
        eq_(Summary.objects.filter(user=self.user).count(), 0)
        eq_(Session.objects.filter(user=self.user).count(), 0)
        eq_(Sleep.objects.filter(user=self.user).count(), 0)
        sleep_range = ('2014-05-01', '2014-05-31')
        sleep_mock = JsonMock('sleep_sleeps', date_range=sleep_range)
        with HTTMock(JsonMock().profile_http,
                     JsonMock().device_http,
                     JsonMock('summary_detail').summary_http,
                     JsonMock('goal_goals').goal_http,
                     JsonMock('session_sessions').session_http,
                     sleep_mock.sleep_http):
            with patch('celery.app.task.Task.delay') as mock_delay:
                mock_delay.side_effect = import_historical_cls
                import_historical(self.misfit_user)

        eq_(Profile.objects.filter(user=self.user).count(), 1)
        eq_(Device.objects.filter(user=self.user).count(), 1)
        eq_(Goal.objects.filter(user=self.user).count(), 2 * 5)
        eq_(Summary.objects.filter(user=self.user).count(), 3)
        eq_(Session.objects.filter(user=self.user).count(), 2 * 5)
        eq_(Sleep.objects.filter(user=self.user).count(), 1)
        eq_(SleepSegment.objects.filter(sleep__user=self.user).count(), 2)

    @freeze_time("2014-07-02 10:52:00", tz_offset=0)
    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('celery.app.task.Task.delay')
    @patch('celery.app.task.Task.retry')
    @patch('misfit.Misfit.device')
    @patch('logging.Logger.debug')
    def test_import_historical_rate_limit(self, mock_dbg, mock_dev,
                                          mock_retry, mock_delay, mock_sig):
        mock_delay.side_effect = lambda a1, a2: import_historical_cls(a1, a2)
        eq_(Profile.objects.filter(user=self.user).count(), 0)
        eq_(Device.objects.filter(user=self.user).count(), 0)
        resp = MagicMock()
        resp.headers = {'x-ratelimit-reset': 1404298869}
        exc = misfit_exceptions.MisfitRateLimitError(429, '', resp)
        mock_dev.side_effect = exc
        mock_retry.side_effect = BaseException
        with HTTMock(JsonMock().profile_http, JsonMock().device_http):
            try:
                import_historical(self.misfit_user)
                assert False, 'Should have thrown an exception'
            except BaseException:
                assert True
        mock_dev.assert_called_once_with()
        mock_retry.assert_called_once_with(countdown=549)
        eq_(Profile.objects.filter(user=self.user).count(), 1)
        eq_(Device.objects.filter(user=self.user).count(), 0)

    @patch('logging.Logger.exception')
    @patch('celery.app.task.Task.delay')
    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('misfitapp.utils.create_misfit')
    def test_import_historical_unknown_error(self, mock_create, mock_sig,
                                             mock_delay, mock_exc):
        """ Test that the notification task handles unknown errors ok """
        # Check that we fail gracefully when we run into an unknown error
        mock_delay.side_effect = lambda a1, a2: import_historical_cls(a1, a2)
        mock_create.side_effect = Exception('FAKE EXCEPTION')
        try:
            import_historical(self.misfit_user)
            assert False, 'We should have raised an exception'
        except Reject:
            assert True
        mock_exc.assert_called_once_with(
            'Unknown exception importing data: FAKE EXCEPTION')
        eq_(Profile.objects.filter(user=self.user).count(), 0)
        eq_(Device.objects.filter(user=self.user).count(), 0)

    @patch('misfit.notification.MisfitNotification.verify_signature')
    def test_import_sleep(self, verify_signature_mock):
        """ Test that calls to import sleeps are idempotent. """
        misfit = utils.create_misfit(
            access_token=self.misfit_user.access_token)
        uuid = self.user.id
        with HTTMock(JsonMock('sleep_sleeps').sleep_http):
            Sleep.import_all_from_misfit(misfit, uuid)
            Sleep.import_all_from_misfit(misfit, uuid)


class TestNotificationTask(MisfitTestBase):
    def setUp(self):
        super(TestNotificationTask, self).setUp()
        self.subscription_content = {
            "Type": "SubscriptionConfirmation",
            "MessageId": "165545c9-xxxx-472c-8df2-xxxxxxxxxxx",
            "Token": "xxxx",
            "TopicArn": "arn:aws:sns:us-east-1:123456789012:MyTopic",
            "Message": "You have chosen to subscribe to the topic...",
            "SubscribeURL": "https://example-subscribe-url.com",
            "Timestamp": "2012-04-26T20:45:04.751Z",
            "SignatureVersion": "1",
            "Signature": "EXAMPLEpH+xxxxx+xxxxx=",
            "SigningCertURL": "xxxxxxx"
        }
        self.notification_content = {
            'Type': 'Notification',
            'MessageId': '2860c564-624b-52ed-a445-8e2b6275b0fa',
            'TopicArn': 'arn:aws:sns:us-east-1:819895241319:resource-tp1',
            'Message': json.dumps([{
                "type": "profiles",
                "action": "updated",
                "id": "1234",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }, {
                "type": "goals",
                "action": "updated",
                "id": "51a4189acf12e53f81000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 13:00:00 UTC"
            }, {
                "type": "goals",
                "action": "updated",
                "id": "51a4189acf12e53f81000002",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 13:00:00 UTC"
            }]),
            'Timestamp': '2014-01-14T09:06:06.756Z',
            'SignatureVersion': '1',
            'Signature': 'xxxxx/xxxxxx/xxxx==',
            'SigningCertURL': 'xxxxxxxx',
            'UnsubscribeURL': 'https://xxxx'
        }

    @patch('misfit.notification.MisfitNotification.verify_signature')
    def test_subscription_confirmation(self, verify_signature_mock):
        """
        Check that a task gets created to handle subscription confirmation
        """
        verify_signature_mock.return_value = None
        content = json.dumps(self.subscription_content).encode('utf8')
        with HTTMock(sns_subscribe):
            with patch('celery.app.task.Task.delay') as mock_delay:
                mock_delay.side_effect = lambda arg: process_notification(arg)
                self.client.post(reverse('misfit-notification'), data=content,
                                 content_type='application/json')
                mock_delay.assert_called_once_with(content)
        verify_signature_mock.assert_called_once_with()
        self.assertEqual(Goal.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)
        self.assertEqual(Summary.objects.count(), 0)

    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('celery.app.task.Task.delay')
    def test_notification(self, mock_delay, verify_signature_mock):
        """
        Check that a task gets created to handle notification
        """
        mock_delay.side_effect = lambda arg: process_notification(arg)
        verify_signature_mock.return_value = None
        with HTTMock(JsonMock().goal_http,
                     JsonMock().profile_http,
                     JsonMock('summary_detail').summary_http):
            content = json.dumps(self.notification_content).encode('utf8')
            self.client.post(reverse('misfit-notification'), data=content,
                             content_type='application/json')
        mock_delay.assert_called_once_with(content)
        eq_(Goal.objects.filter(user=self.user).count(), 2)
        eq_(Profile.objects.filter(user=self.user).count(), 1)
        eq_(Summary.objects.filter(user=self.user).count(), 3)

    @freeze_time("2014-07-02 10:52:00", tz_offset=0)
    @patch('logging.Logger.debug')
    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('celery.app.task.Task.delay')
    @patch('misfit.Misfit.goal')
    @patch('celery.app.task.Task.retry')
    def test_notification_rate_limit(self, mock_retry, mock_goal, mock_delay,
                                     verify_signature_mock, debug_mock):
        """ Test that the notification task rate limit errors ok """
        # Check that we fail gracefully when we hit the rate limit
        mock_delay.side_effect = lambda arg: process_notification(arg)
        resp = MagicMock()
        resp.headers = {'x-ratelimit-reset': 1404298869}
        exc = misfit_exceptions.MisfitRateLimitError(429, '', resp)
        mock_goal.side_effect = exc
        mock_retry.side_effect = Exception
        with HTTMock(JsonMock().profile_http):
            try:
                content = json.dumps(self.notification_content).encode('utf8')
                self.client.post(reverse('misfit-notification'), data=content,
                                 content_type='application/json')
                assert False, 'We should have raised an exception'
            except Exception:
                assert True
        mock_delay.assert_called_once_with(content)
        mock_goal.assert_called_once_with(object_id='51a4189acf12e53f81000001')
        mock_retry.assert_called_once_with(countdown=549)
        eq_(Goal.objects.filter(user=self.user).count(), 0)
        eq_(Profile.objects.filter(user=self.user).count(), 1)
        eq_(Summary.objects.filter(user=self.user).count(), 0)

    @patch('logging.Logger.exception')
    @patch('celery.app.task.Task.delay')
    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('misfitapp.utils.create_misfit')
    def test_notification_unknown_error(self, mock_create, mock_sig,
                                        mock_delay, mock_exc):
        """ Test that the notification task handles unknown errors ok """
        # Check that we fail gracefully when we run into an unknown error
        mock_delay.side_effect = lambda arg: process_notification(arg)
        mock_create.side_effect = Exception('FAKE EXCEPTION')
        try:
            content = json.dumps(self.notification_content).encode('utf8')
            self.client.post(reverse('misfit-notification'), data=content,
                             content_type='application/json')
            assert False, 'We should have raised an exception'
        except Reject:
            assert True
        mock_exc.assert_called_once_with(
            'Unknown exception processing notification: FAKE EXCEPTION')
        eq_(Goal.objects.filter(user=self.user).count(), 0)
        eq_(Profile.objects.filter(user=self.user).count(), 0)
        eq_(Summary.objects.filter(user=self.user).count(), 0)

    @patch('misfit.notification.MisfitNotification.verify_signature')
    @patch('celery.app.task.Task.delay')
    @patch('logging.Logger.warning')
    def test_notification_no_user(self, mock_warning, mock_delay, mock_sig):
        """ Test that the notification task handles missing users """
        # Check that we fail gracefully when the user doesn't exist on our end
        mock_delay.side_effect = lambda arg: process_notification(arg)
        MisfitUser.objects.all().delete()
        with HTTMock(JsonMock().goal_http, JsonMock().profile_http,
                     JsonMock('summary_detail').summary_http):
            content = json.dumps(self.notification_content).encode('utf8')
            self.client.post(reverse('misfit-notification'), data=content,
                             content_type='application/json')
        mock_delay.assert_called_once_with(content)
        mock_warning.assert_has_calls([call(
            'Received a notification for a user who is not in our database '
            'with id: %s' % self.misfit_user_id)] * 3)
        eq_(Goal.objects.filter(user=self.user).count(), 0)
        eq_(Profile.objects.filter(user=self.user).count(), 0)
        eq_(Summary.objects.filter(user=self.user).count(), 0)

    def test_device(self):

        # Create
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Device.objects.all().count(), 0)
        with HTTMock(JsonMock().device_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "devices",
                "action": "created",
                "id": "21a4189acf12e53f81000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Device.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Device.objects.all().count(), 1)
        eq_(Device.objects.all()[0].user_id, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().device_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "devices",
                "action": "updated",
                "id": "548b1b3d33822a17a23f4e62",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Device.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = {
            "type": "devices",
            "action": "deleted",
            "id": "548b1b3d33822a17a23f4e62",
            "ownerId": self.misfit_user_id,
            "updatedAt": "2014-10-17 12:00:00 UTC"
        }
        Device.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 0)

    def test_goal(self):
        # Create
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Goal.objects.all().count(), 0)
        with HTTMock(JsonMock().goal_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "goals",
                "action": "created",
                "id": "548b1b3d33822a17a23f4e62",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Goal.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Goal.objects.all().count(), 1)
        eq_(Goal.objects.all()[0].user_id, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().goal_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "goals",
                "action": "updated",
                "id": "548b1b3d33822a17a23f4e62",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Goal.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = {
            "type": "goals",
            "action": "deleted",
            "id": "548b1b3d33822a17a23f4e62",
            "ownerId": self.misfit_user_id,
            "updatedAt": "2014-10-17 12:00:00 UTC"
        }
        Goal.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 0)

    def test_profile(self):

        # Create
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Profile.objects.all().count(), 0)
        with HTTMock(JsonMock().profile_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "profiles",
                "action": "created",
                "id": "11a4189acf12e53f81000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Profile.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Profile.objects.all().count(), 1)
        eq_(Profile.objects.all()[0].user_id, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().profile_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "profiles",
                "action": "updated",
                "id": "11a4189acf12e53f81000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Profile.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = {
            "type": "profiles",
            "action": "deleted",
            "id": "11a4189acf12e53f81000001",
            "ownerId": self.misfit_user_id,
            "updatedAt": "2014-10-17 12:00:00 UTC"
        }
        Profile.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 0)

    def test_session(self):

        # Create
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Session.objects.all().count(), 0)
        with HTTMock(JsonMock().session_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "sessions",
                "action": "created",
                "id": "548fa26c5c392c2ff6000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Session.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Session.objects.all().count(), 1)
        eq_(Session.objects.all()[0].user_id, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().session_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "sessions",
                "action": "updated",
                "id": "548fa26c5c392c2ff6000001",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Session.process_message(
                MisfitMessage(message), misfit, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = {
            "type": "sessions",
            "action": "deleted",
            "id": "548fa26c5c392c2ff6000001",
            "ownerId": self.misfit_user_id,
            "updatedAt": "2014-10-17 12:00:00 UTC"
        }
        Session.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 0)

    @patch('misfit.notification.MisfitNotification.verify_signature')
    def test_sleep(self, verify_signature_mock):

        # Create
        eq_(Sleep.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Sleep.objects.all().count(), 0)
        with HTTMock(JsonMock().sleep_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "sleeps",
                "action": "created",
                "id": "548f84cd33822a9b48061f19",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Sleep.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Sleep.objects.all().count(), 1)
        sleep = Sleep.objects.all()[0]
        eq_(sleep.user_id, self.user.pk)
        eq_(Sleep.objects.filter(user_id=self.user.pk).count(), 1)
        eq_(SleepSegment.objects.filter(sleep=sleep).count(), 4)

        # Update
        with HTTMock(JsonMock().sleep_http):
            misfit = utils.create_misfit(
                access_token=self.misfit_user.access_token)
            message = {
                "type": "sleeps",
                "action": "updated",
                "id": "548f84cd33822a9b48061f19",
                "ownerId": self.misfit_user_id,
                "updatedAt": "2014-10-17 12:00:00 UTC"
            }
            Sleep.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Sleep.objects.filter(user_id=self.user.pk).count(), 1)
        eq_(SleepSegment.objects.filter(sleep=sleep).count(), 4)

        # Delete
        message = {
            "type": "sleeps",
            "action": "deleted",
            "id": "548f84cd33822a9b48061f19",
            "ownerId": self.misfit_user_id,
            "updatedAt": "2014-10-17 12:00:00 UTC"
        }
        Sleep.process_message(MisfitMessage(message), misfit, self.user.pk)
        eq_(Sleep.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(SleepSegment.objects.filter(sleep=sleep).count(), 0)
