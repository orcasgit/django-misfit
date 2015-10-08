from freezegun import freeze_time
from misfit.notification import MisfitMessage
from misfitapp.models import (
    Device,
    Goal,
    MisfitModel,
    MisfitUser,
    Profile,
    Sleep,
    SleepSegment,
    Session,
    Summary
)
import datetime

from .base import MisfitTestBase


class TestMisfitModels(MisfitTestBase):

    @freeze_time("2014-12-12 22:00:01")
    def setUp(self):
        self.today = datetime.date.today()
        self.now = datetime.datetime.now()
        super(TestMisfitModels, self).setUp()

    def test_misfit_model(self):
        """ Test MisfitModel """
        with self.assertRaises(NotImplementedError):
            MisfitModel.import_from_misfit(None, None)
        with self.assertRaises(NotImplementedError):
            MisfitModel.import_all_from_misfit(None, None)
        msg = MisfitMessage({'action': 'UNKNOWN_ACTION'})
        error_msg = 'Unknown message action: UNKNOWN_ACTION'
        with self.assertRaisesRegexp(Exception, error_msg):
            MisfitModel.process_message(msg, None, None)

    def test_misfit_user(self):
        """ MisfitUser was already created in base, now test the properties """
        self.assertEqual(self.misfit_user.user, self.user)
        self.assertEqual(self.misfit_user.__str__(), self.username)
        self.assertEqual(self.misfit_user.last_update, None)
        self.assertEqual(self.misfit_user.access_token, self.access_token)
        self.assertEqual(self.misfit_user.misfit_user_id, self.misfit_user_id)

    def test_summary(self):
        """ Test the Summary Model """
        data = {'user_id': self.user.pk,
                'date': self.today,
                'points': 3.3,
                'steps': 3400,
                'calories': 3000,
                'activity_calories': 2000,
                'distance': 2.4,
        }

        s = Summary(**data)
        s.save()
        self.assertEqual('%s' % s, '2014-12-12: 3400')

    def test_profile(self):
        """ Test the Profile Model """

        data = {'user_id': self.user.pk,
                'email': 'test@example.com',
                'birthday': self.today,
                'gender': 'male',
        }
        p = Profile(**data)
        p.save()
        self.assertEqual(p.email, data['email'])
        self.assertEqual('%s' % p, p.email)

    def test_device(self):
        """ Test the Device Model """
        data = {'id': self.random_string(24),
                'user_id': self.user.pk,
                'device_type': 'shine',
                'serial_number': self.random_string(10),
                'firmware_version': self.random_string(40),
                'battery_level': 44,
        }
        d = Device(**data)
        d.save()
        self.assertEqual(d.serial_number, data['serial_number'])
        self.assertEqual('%s' % d, 'shine: %s' % data['serial_number'])

    def test_goal(self):
        """ Test the Goal Model """
        data = {'id': self.random_string(24),
                'user_id': self.user.pk,
                'date': self.today,
                'points': 64.2,
                'target_points': 200,
        }
        g = Goal(**data)
        g.save()
        self.assertEqual('%s' % g, '%s 2014-12-12 64.2 of 200' % data['id'])

    def test_session(self):
        """ Test the Session Model """
        data = {'id': self.random_string(24),
                'user_id': self.user.pk,
                'activity_type': 'soccer',
                'start_time': self.now,
                'duration': 300,
                'steps': 20,
        }
        s = Session(**data)
        s.save()
        self.assertEqual('%s' % s, '2014-12-12 22:00:01 300 soccer')

    def test_sleep(self):
        """ Test the Sleep and Sleep Segment model """
        data = {'id': self.random_string(24),
                'user_id': self.user.pk,
                'auto_detected': True,
                'start_time': self.now,
                'duration': 300,
        }
        sleep = Sleep(**data)
        sleep.save()
        self.assertEqual(
            '%s' % sleep, '%s %s' % (sleep.start_time, sleep.duration))

        seg_data = {'sleep': sleep,
                    'time': data['start_time'],
                    'sleep_type': SleepSegment.SLEEP,
        }
        seg = SleepSegment(**seg_data)
        seg.save()
        self.assertEqual('%s' % seg, '%s %s' % (seg.time, seg.sleep_type))
