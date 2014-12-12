from misfitapp.models import (
    Device,
    Goal,
    MisfitUser,
    Profile,
    Sleep,
    SleepSegment
    Session,
    Summary
)
import datetime

from .base import MisfitTestBase


class TestMisfitModels(MisfitTestBase):

    today = datetime.date.today()
    now = datetime.datetime.now()

    def test_misfit_user(self):
        """ MisfitUser was already created in base, now test the properties """
        self.assertEqual(self.misfit_user.user, self.user)
        self.assertEqual(self.misfit_user.__str__(), self.username)
        self.assertEqual(self.misfit_user.last_update, None)
        self.assertEqual(self.misfit_user.access_token, self.access_token)
        self.assertEqual(self.misfit_user.misfit_user_id, self.misfit_user_id)

    def test_summary(self):
        """ Test the Summary Model """
        data = {'misfit_user': self.misfit_user,
                'start_date': self.today,
                'end_date': self.today,
                'points': 3.3,
                'steps': 3400,
                'calories': 3000,
                'activity_calories': 2000,
                'distance': 2.4,
        }

        s = Summary(**data)
        s.save()

    def test_profile(self):
        """ Test the Profile Model """

        data = {'misfit_user': self.misfit_user,
                'email': 'test@example.com',
                'birthday': self.today,
                'gender': 'male',
        }
        p = Profile(**data)
        p.save()

    def test_device(self):
        """ Test the Device Model """
        data = {'id': self.random_string(24),
                'misfit_user': self.misfit_user,
                'device_type': 'shine',
                'serial_number': self.random_string(10),
                'firmware_version': self.random_string(40),
                'batteryLevel': 44,
        }
        d = Device(**data)
        d.save()

    def test_goal(self):
        """ Test the Goal Model """
        data = {'id': self.random_string(24),
                'misfit_user': self.misfit_user,
                'date': self.today,
                'points': 64.2,
                'target_points': 200,
        }
        g = Goal(**data)
        g.save()

    def test_session(self):
        """ Test the Session Model """
        data = {'id': self.random_string(24),
                'misfit_user': self.misfit_user,
                'activity_type': 'soccer',
                'start_time': self.now,
                'duration': 300,
                'steps': 20,
        }
        s = Session(**data)
        s.save()

    def test_sleep(self):
        """ Test the Sleep and Sleep Segment model """
        data = {'id': self.random_string(24),
                'misfit_user': self.misfit_user,
                'auto_detected': True,
                'start_time': self.now,
                'duration': 300,
        }
        sleep = Sleep(**data)
        sleep.save()

        seg_data = {'sleep': sleep,
                    'time': data['start_time'],
                    'sleep_type': SleepSegment.SLEEP,
        }
        seg = SleepSegment(**seg_data)
        seg.save()
