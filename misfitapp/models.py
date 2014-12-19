from django.conf import settings
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from math import pow
import datetime

from .extras import cc_to_underscore_keys, chunkify_dates

MAX_KEY_LEN = 24
UserModel = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


@python_2_unicode_compatible
class MisfitUser(models.Model):
    user = models.ForeignKey(UserModel)
    misfit_user_id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    access_token = models.TextField()
    last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if hasattr(self.user, 'get_username'):
            return self.user.get_username()
        else:  # Django 1.4
            return self.user.username


@python_2_unicode_compatible
class Summary(models.Model):
    user = models.ForeignKey(UserModel)
    date = models.DateField()
    points = models.FloatField()
    steps = models.IntegerField()
    calories = models.FloatField()
    activity_calories = models.FloatField()
    distance = models.FloatField()

    def __str__(self):
        return '%s: %s' % (self.date.strftime('%Y-%m-%d'), self.steps)

    class Meta:
        unique_together = ('user', 'date')

    @classmethod
    def create_from_misfit(cls, misfit, uid, start_date=datetime.date(2014,1,1), end_date=datetime.date.today()):
        """
        Imports all Summary data from misfit for the specified date range, chunking API
        calls if needed.
        """
        # Keep track of the data we already have
        exists = cls.objects.filter(user_id=uid,
                                    date__gte=start_date,
                                    date__lte=end_date).values_list('date', flat=True)
        obj_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            summaries = misfit.summary(start_date=start, end_date=end, detail=True)
            for summary in summaries:
                if summary.date.date() not in exists:
                    data = cc_to_underscore_keys(summary.data)
                    data['user_id'] = uid
                    obj_list.append(cls(**data))
        cls.objects.bulk_create(obj_list)


@python_2_unicode_compatible
class Profile(models.Model):
    GENDER_TYPES = (('male', 'male'), ('female', 'female'))

    user = models.ForeignKey(UserModel, unique=True)
    email = models.EmailField()
    birthday = models.DateField()
    gender = models.CharField(choices=GENDER_TYPES, max_length=6)
    name = models.TextField()

    def __str__(self):
        return self.email

    @classmethod
    def create_from_misfit(cls, misfit, uid):
        if not cls.objects.filter(user_id=uid).exists():
            profile = misfit.profile()
            data = cc_to_underscore_keys(profile.data)
            data['user_id'] = uid
            cls(**data).save()


@python_2_unicode_compatible
class Device(models.Model):
    DEVICE_TYPES = (('shine', 'shine'),)

    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    device_type = models.CharField(choices=DEVICE_TYPES, max_length=5)
    serial_number = models.CharField(max_length=100)
    firmware_version = models.CharField(max_length=100)
    battery_level = models.SmallIntegerField()

    def __str__(self):
        return '%s: %s' % (self.device_type, self.serial_number)

    @classmethod
    def create_from_misfit(cls, misfit, uid):
        if not cls.objects.filter(user_id=uid).exists():
            device = misfit.device()
            data = cc_to_underscore_keys(device.data)
            data['user_id'] = uid
            cls(**data).save()


@python_2_unicode_compatible
class Goal(models.Model):
    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    date = models.DateField()
    points = models.FloatField()
    target_points = models.IntegerField()
    time_zone_offset = models.SmallIntegerField(default=0)

    def __str__(self):
        return '%s %s %s of %s' % (self.id, self.date, self.points,
                                   self.target_points)

    class Meta:
        unique_together = ('user', 'date')

    @classmethod
    def create_from_misfit(cls, misfit, uid, start_date=datetime.date(2014,1,1), end_date=datetime.date.today()):
        """
        Imports all Goal data from misfit for the specified date range, chunking API
        calls if needed.
        """
        # Keep track of the data we already have
        exists = cls.objects.filter(user_id=uid,
                                    date__gte=start_date,
                                    date__lte=end_date).values_list('date', flat=True)
        obj_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            goals = misfit.goal(start_date=start, end_date=end)
            for goal in goals:
                if goal.date.date() not in exists:
                    data = cc_to_underscore_keys(goal.data)
                    data['user_id'] = uid
                    obj_list.append(cls(**data))
        cls.objects.bulk_create(obj_list)


@python_2_unicode_compatible
class Session(models.Model):
    ACTIVITY_TYPES = (('cycling', 'cycling'),
                      ('swimming', 'swimming'),
                      ('walking', 'walking'),
                      ('tennis', 'tennis'),
                      ('basketball', 'basketball'),
                      ('soccer', 'soccer'))

    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    activity_type = models.CharField(choices=ACTIVITY_TYPES, max_length=15)
    start_time = models.DateTimeField()
    duration = models.IntegerField()
    points = models.FloatField(null=True)
    steps = models.IntegerField(null=True)
    calories = models.FloatField(null=True)
    distance = models.FloatField(null=True)

    def __str__(self):
        return '%s %s %s' % (self.start_time, self.duration,
                             self.activity_type)
    class Meta:
        unique_together = ('user', 'start_time')

    @classmethod
    def create_from_misfit(cls, misfit, uid, start_date=datetime.date(2014,1,1), end_date=datetime.date.today()):
        """
        Imports all Session data from misfit for the specified date range, chunking API
        calls if needed.
        """
        # Keep track of the data we already have
        exists = cls.objects.filter(user_id=uid,
                                    start_time__gte=start_date,
                                    start_time__lte=end_date).values_list('start_time', flat=True)
        obj_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            sessions = misfit.session(start_date=start, end_date=end)
            for session in sessions:
                if session.startTime not in exists:
                    data = cc_to_underscore_keys(session.data)
                    data['user_id'] = uid
                    obj_list.append(cls(**data))
        cls.objects.bulk_create(obj_list)


@python_2_unicode_compatible
class Sleep(models.Model):
    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    auto_detected = models.BooleanField()
    start_time = models.DateTimeField()
    duration = models.IntegerField()

    def __str__(self):
        return '%s %s' % (self.start_time, self.duration)

    class Meta:
        unique_together = ('user', 'start_time')

    @classmethod
    def create_from_misfit(cls, misfit, uid, start_date=datetime.date(2014,1,1), end_date=datetime.date.today()):
        """
        Imports all Sleep and Sleep Segment data from misfit for the specified date range,
        chunking API calls if needed.
        """
        # Keep track of the data we already have
        exists = cls.objects.filter(user_id=uid,
                                    start_time__gte=start_date,
                                    start_time__lte=end_date).values_list('start_time', flat=True)
        seg_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            sleeps = misfit.sleep(start_date=start, end_date=end)
            for sleep in sleeps:
                if sleep.startTime not in exists:
                    data = cc_to_underscore_keys(sleep.data)
                    data['user_id'] = uid
                    segments = data.pop('sleep_details')
                    s = cls(**data)
                    s.save()
                    for seg in segments:
                        seg_list.append(SleepSegment(sleep=s,
                                                     time=seg['datetime'],
                                                     sleep_type=seg['value']))


        SleepSegment.objects.bulk_create(seg_list)


@python_2_unicode_compatible
class SleepSegment(models.Model):
    AWAKE = 1
    SLEEP = 2
    DEEP_SLEEP = 3
    SLEEP_TYPES = ((AWAKE, 'awake'), (SLEEP, 'sleep'), (DEEP_SLEEP, 'deep sleep'))

    sleep = models.ForeignKey(Sleep)
    time = models.DateTimeField()
    sleep_type = models.SmallIntegerField(choices=SLEEP_TYPES)

    def __str__(self):
        return '%s %s' % (self.time, self.sleep_type)

    class Meta:
        unique_together = ('sleep', 'time')
