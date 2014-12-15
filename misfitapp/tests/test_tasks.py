from __future__ import absolute_import

import arrow
import celery
import json
import sys

from django.core.cache import cache
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from freezegun import freeze_time
from httmock import HTTMock, urlmatch
from misfit import exceptions as misfit_exceptions
from misfit import Misfit
from mock import MagicMock, patch
from nose.tools import eq_

from misfitapp import utils
from misfitapp.models import MisfitUser, Goal, Profile, Summary
from misfitapp.tasks import process_notification

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
    def __init__(self, file_name_base=None):
        """ Build the response template """
        self.headers = {'content-type': 'application/json; charset=utf-8'}
        self.response_tmpl = {'status_code': 200, 'headers': self.headers}
        self.file_name_base = file_name_base

    def json_file(self):
        response = self.response_tmpl
        file_path = 'misfitapp/tests/responses/%s.json' % self.file_name_base
        with open(file_path) as json_file:
            response['content'] = json_file.read().encode('utf8')
        return response

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/goals/.*')
    def goal_http(self, url, *args):
        """ Method to return the contents of a goal json file """
        self.file_name_base = 'goal_' + url.path.split('/')[-2]
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


class TestNotificationTask(MisfitTestBase):
    def setUp(self):
        super(TestNotificationTask, self).setUp()
        self.subscription_content = {
            "Type" : "SubscriptionConfirmation",
            "MessageId" : "165545c9-xxxx-472c-8df2-xxxxxxxxxxx",
            "Token" : "xxxx",
            "TopicArn" : "arn:aws:sns:us-east-1:123456789012:MyTopic",
            "Message" : "You have chosen to subscribe to the topic...",
            "SubscribeURL" : "https://example-subscribe-url.com",
            "Timestamp" : "2012-04-26T20:45:04.751Z",
            "SignatureVersion" : "1",
            "Signature" : "EXAMPLEpH+xxxxx+xxxxx=",
            "SigningCertURL" : "xxxxxxx"
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
            self.client.post(reverse('misfit-notification'), data=content,
                             content_type='application/json')
        verify_signature_mock.assert_called_once_with()
        self.assertEqual(Goal.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)
        self.assertEqual(Summary.objects.count(), 0)

    @patch('misfit.notification.MisfitNotification.verify_signature')
    def test_notification(self, verify_signature_mock):
        """
        Check that a task gets created to handle notification
        """
        verify_signature_mock.return_value = None
        content = json.dumps(self.notification_content).encode('utf8')
        with HTTMock(JsonMock().goal_http,
                     JsonMock('summary_detail').summary_http):
            self.client.post(reverse('misfit-notification'), data=content,
                             content_type='application/json')
        eq_(Summary.objects.filter(misfit_user=self.misfit_user).count(), 3)
