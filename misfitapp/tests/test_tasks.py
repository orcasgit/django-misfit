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
from misfitapp.models import MisfitUser, Device, Goal, Profile, Session, Summary
from misfitapp.tasks import (
    process_notification,
    process_device,
    process_goal,
    process_profile,
    process_session,
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
              path='/move/resource/v1/user/me/device/.*')
    def device_http(self, url, *args):
        """ Method to return the contents of a device json file """
        self.file_name_base = 'device'
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/goals/.*')
    def goal_http(self, url, *args):
        """ Method to return the contents of a goal json file """
        self.file_name_base = 'goal_' + url.path.split('/')[-2]
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/me/activity/sessions/.*')
    def session_http(self, url, *args):
        """ Method to return the contents of a session json file """
        self.file_name_base = 'session_' + url.path.split('/')[-2]
        return self.json_file()

    @urlmatch(scheme='https', netloc=r'api\.misfitwearables\.com',
              path='/move/resource/v1/user/.*/profile/*')
    def profile_http(self, url, *args):
        """ Method to return the contents of a profile json file """
        self.file_name_base = 'profile'
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
        eq_(Goal.objects.filter(user=self.user).count(), 2)
        eq_(Profile.objects.filter(user=self.user).count(), 1)
        eq_(Summary.objects.filter(user=self.user).count(), 3)


    def test_device(self):

        # Create
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Device.objects.all().count(), 0)
        with HTTMock(JsonMock().device_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "devices",
                        "action": "created",
                        "id": "21a4189acf12e53f81000001",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_device(message, misfit, self.user.pk)
        eq_(Device.objects.all().count(), 1)
        eq_(Device.objects.all()[0].user_id, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().device_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "devices",
                        "action": "updated",
                        "id": "548b1b3d33822a17a23f4e62",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_device(message, misfit, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = { "type": "devices",
                    "action": "deleted",
                    "id": "548b1b3d33822a17a23f4e62",
                    "ownerId": self.misfit_user_id,
                    "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
        process_device(message, misfit, self.user.pk)
        eq_(Device.objects.filter(user_id=self.user.pk).count(), 0)


    def test_goal(self):

        # Create
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Goal.objects.all().count(), 0)
        with HTTMock(JsonMock().goal_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "goals",
                        "action": "created",
                        "id": "548b1b3d33822a17a23f4e62",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_goal(message, misfit, self.user.pk)
        eq_(Goal.objects.all().count(), 1)
        eq_(Goal.objects.all()[0].user_id, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().goal_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "goals",
                        "action": "updated",
                        "id": "548b1b3d33822a17a23f4e62",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_goal(message, misfit, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = { "type": "goals",
                    "action": "deleted",
                    "id": "548b1b3d33822a17a23f4e62",
                    "ownerId": self.misfit_user_id,
                    "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
        process_goal(message, misfit, self.user.pk)
        eq_(Goal.objects.filter(user_id=self.user.pk).count(), 0)
 
    def test_profile(self):

        # Create
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Profile.objects.all().count(), 0)
        with HTTMock(JsonMock().profile_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "profiles",
                        "action": "created",
                        "id": "11a4189acf12e53f81000001",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_profile(message, misfit, self.user.pk)
        eq_(Profile.objects.all().count(), 1)
        eq_(Profile.objects.all()[0].user_id, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().profile_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "profiles",
                        "action": "updated",
                        "id": "11a4189acf12e53f81000001",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_profile(message, misfit, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = { "type": "profiles",
                    "action": "deleted",
                    "id": "11a4189acf12e53f81000001",
                    "ownerId": self.misfit_user_id,
                    "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
        process_profile(message, misfit, self.user.pk)
        eq_(Profile.objects.filter(user_id=self.user.pk).count(), 0)


    def test_session(self):

        # Create
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 0)
        eq_(Session.objects.all().count(), 0)
        with HTTMock(JsonMock().session_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "sessions",
                        "action": "created",
                        "id": "548fa26c5c392c2ff6000001",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_session(message, misfit, self.user.pk)
        eq_(Session.objects.all().count(), 1)
        eq_(Session.objects.all()[0].user_id, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 1)

        # Update
        with HTTMock(JsonMock().session_http):
            misfit = utils.create_misfit(access_token=self.misfit_user.access_token)
            message = { "type": "sessions",
                        "action": "updated",
                        "id": "548fa26c5c392c2ff6000001",
                        "ownerId": self.misfit_user_id,
                        "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
            process_session(message, misfit, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 1)

        # Delete
        message = { "type": "sessions",
                    "action": "deleted",
                    "id": "548fa26c5c392c2ff6000001",
                    "ownerId": self.misfit_user_id,
                    "updatedAt": "2014-10-17 12:00:00 UTC"
                    }
        process_session(message, misfit, self.user.pk)
        eq_(Session.objects.filter(user_id=self.user.pk).count(), 0)


    def test_sleep(self):
        pass
