from django.conf import settings
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from math import pow

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


@python_2_unicode_compatible
class Goal(models.Model):
    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    date = models.DateField()
    points = models.FloatField()
    target_points = models.IntegerField()

    def __str__(self):
        return '%s %s %s of %s' % (self.id, self.date, self.points,
                                   self.target_points)


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


@python_2_unicode_compatible
class Sleep(models.Model):
    id = models.CharField(max_length=MAX_KEY_LEN, primary_key=True)
    user = models.ForeignKey(UserModel)
    auto_detected = models.BooleanField()
    start_time = models.DateTimeField()
    duration = models.IntegerField()

    def __str__(self):
        '%s %s' % (start_time, duration)


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
        '%s %s' % (time, sleep_type)
