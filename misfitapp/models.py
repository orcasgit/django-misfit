from django.conf import settings
from django.db import models, IntegrityError
from django.utils.encoding import python_2_unicode_compatible
from math import pow
from misfit.notification import MisfitMessage
import datetime

DAYS_IN_CHUNK = 30
MAX_KEY_LEN = 24
MISFIT_HISTORIC_TIMEDELTA = getattr(settings, 'MISFIT_HISTORIC_TIMEDELTA',
                                    datetime.timedelta(days=90))
HISTORIC_START_DATE = datetime.date.today() - MISFIT_HISTORIC_TIMEDELTA
UserModel = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


def chunkify_dates(start, end, days_in_chunk=DAYS_IN_CHUNK):
    """
    Return a list of tuples that chunks the date range into ranges
    of length days_in_chunk, inclusive of the end date. So the end
    date of one chunk is equal to the start date of the chunk after.
    """
    chunks = []
    s = start
    e = start + datetime.timedelta(days=days_in_chunk)
    while e - datetime.timedelta(days=days_in_chunk) < end:
        e = min(e, end)
        chunks.append((s, e))
        s = e
        e = s + datetime.timedelta(days=days_in_chunk)
    return chunks


def dedupe_by_field(l, field):
    """
    Returns a new list with duplicate objects removed. Objects are equal
    iff the have the same value for 'field'.
    """
    d = dict((getattr(obj, field), obj) for obj in l)
    return list(d.values())


class MisfitModel(models.Model):
    class Meta:
        abstract = True

    @classmethod
    def process_message(cls, message, misfit, uid):
        if message.action == MisfitMessage.DELETED:
            filters = {'pk': message.id}
            if cls == Profile:
                filters = {'user_id': uid}
            cls.objects.filter(**filters).delete()
        elif message.action in [MisfitMessage.CREATED, MisfitMessage.UPDATED]:
            return cls.import_from_misfit(misfit, uid, object_id=message.id)
        else:
            raise Exception("Unknown message action: %s" % message.action)

    @classmethod
    def import_from_misfit(cls, misfit, uid, **kwargs):
        """ Derived classes should implement this """
        raise NotImplementedError

    @classmethod
    def import_all_from_misfit(cls, misfit, uid):
        """
        This is used to import all data from misfit when a user is initially
        linked. By default it just runs import_from_misfit, but a model with
        more complex needs can override this
        """
        cls.import_from_misfit(misfit, uid)


@python_2_unicode_compatible
class MisfitUser(models.Model):
    """ A user's Misfit credentials, allowing API access """
    user = models.ForeignKey(UserModel, help_text='The user')
    misfit_user_id = models.CharField(
        max_length=MAX_KEY_LEN,
        primary_key=True,
        help_text='The Misfit user ID')
    access_token = models.TextField(help_text='The OAuth access token')
    last_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            'The datetime when the misfit user was last updated (deprecated)'
        ))

    def __str__(self):
        return self.user.get_username()


@python_2_unicode_compatible
class Summary(MisfitModel):
    """
    Misfit daily summary data point:
    https://build.misfit.com/docs/cloudapi/api_references#summary
    """
    user = models.ForeignKey(UserModel, help_text="The summary's user")
    date = models.DateField(help_text='The date of the summary')
    points = models.FloatField(help_text='Points for the day')
    steps = models.IntegerField(help_text='Steps for the day')
    calories = models.FloatField(help_text='Calories for the day')
    activity_calories = models.FloatField(
        help_text='Activity calories for the day')
    distance = models.FloatField(
        help_text='Distance traveled during the day, in miles')

    def __str__(self):
        return '%s: %s' % (self.date.strftime('%Y-%m-%d'), self.steps)

    class Meta:
        unique_together = ('user', 'date')

    @classmethod
    def import_from_misfit(cls, misfit, uid, update=False,
                           start_date=HISTORIC_START_DATE,
                           end_date=datetime.date.today()):
        """
        Imports all Summary data from misfit for the specified date range,
        chunking API calls if needed. If update is True, update existing
        records
        """
        # Keep track of the data we already have
        exists = cls.objects.filter(
            user_id=uid, date__gte=start_date, date__lte=end_date
        ).values_list('date', flat=True)
        date_chunks = chunkify_dates(start_date, end_date, 30)
        obj_list = []
        for start, end in date_chunks:
            summaries = misfit.summary(
                start_date=start, end_date=end, detail=True)
            for summary in summaries:
                if update or summary.date.date() not in exists:
                    data = {
                        'date': summary.date.date(),
                        'points': summary.points,
                        'steps': summary.steps,
                        'calories': summary.calories,
                        'activity_calories': summary.activityCalories,
                        'distance': summary.distance
                    }
                    if update:
                        cls.objects.update_or_create(
                            user_id=uid, date=data['date'], defaults=data)
                    else:
                        obj_list.append(cls(user_id=uid, **data))
        cls.objects.bulk_create(dedupe_by_field(obj_list, 'date'))


@python_2_unicode_compatible
class Profile(MisfitModel):
    """
    Misfit profile information:
    https://build.misfit.com/docs/cloudapi/api_references#profile
    """
    GENDER_TYPES = (('male', 'male'), ('female', 'female'))

    user = models.OneToOneField(
        UserModel,
        related_name='misfit_profile',
        help_text="The profile's user")
    email = models.EmailField(null=True, blank=True, help_text='Email address')
    birthday = models.DateField(help_text="The user's birth date")
    gender = models.CharField(
        choices=GENDER_TYPES,
        max_length=6,
        help_text="The user's gender, one of: {}".format(
            ', '.join([c for c, _ in GENDER_TYPES])
        ))
    name = models.TextField(
        null=True, blank=True, help_text='The name on the profile')
    avatar = models.URLField(
        null=True, blank=True, help_text="URL to the profile's avatar")

    def __str__(self):
        return self.email

    @classmethod
    def import_from_misfit(cls, misfit, uid, object_id=None):
        profile = misfit.profile()
        data = {
            'email': profile.email,
            'birthday': profile.birthday,
            'gender': profile.gender,
            # These two attributes aren't always included in the API results
            # despite the fact that the docs say they are not optional
            'name': getattr(profile, 'name', ''),
            'avatar': getattr(profile, 'avatar', ''),
        }
        return cls.objects.update_or_create(user_id=uid, defaults=data)


@python_2_unicode_compatible
class Device(MisfitModel):
    """
    A Misfit device:
    https://build.misfit.com/docs/cloudapi/api_references#device
    """
    id = models.CharField(
        max_length=MAX_KEY_LEN,
        primary_key=True,
        help_text='The device ID assigned by Misfit')
    user = models.ForeignKey(UserModel, help_text="The device's user")
    device_type = models.CharField(
        max_length=64,
        help_text='The device type as a human readable string')
    serial_number = models.CharField(
        max_length=100, help_text="The device's serial number")
    firmware_version = models.CharField(
        max_length=100, help_text="The version of the device's firmware")
    battery_level = models.SmallIntegerField(
        help_text='Percentage battery remaining')
    last_sync_time = models.DateTimeField(
        null=True, blank=True, help_text='Datetime the device was last synced')

    def __str__(self):
        return '%s: %s' % (self.device_type, self.serial_number)

    @classmethod
    def import_from_misfit(cls, misfit, uid, object_id=None):
        device = misfit.device()
        if not hasattr(device, 'id'):
            # This means the user has no device, fail gracefully
            return False, False
        data = {
            'id': device.id,
            'device_type': device.deviceType,
            'serial_number': device.serialNumber,
            'firmware_version': device.firmwareVersion,
            'battery_level': device.batteryLevel
        }
        # Check for the undocumented lastSyncTime data
        if hasattr(device, 'lastSyncTime') and device.lastSyncTime:
            data['last_sync_time'] = device.lastSyncTime.datetime
        return cls.objects.update_or_create(user_id=uid, defaults=data)


@python_2_unicode_compatible
class Goal(MisfitModel):
    """
    A Misfit goal:
    https://build.misfit.com/docs/cloudapi/api_references#goal
    """
    id = models.CharField(
        max_length=MAX_KEY_LEN,
        primary_key=True,
        help_text='The goal ID assigned by Misfit')
    user = models.ForeignKey(UserModel, help_text="The goal's user")
    date = models.DateField(help_text='Date of the goal')
    points = models.FloatField(
        help_text='Progress points that the user achieved that day')
    target_points = models.IntegerField(help_text='Target points for that day')
    time_zone_offset = models.SmallIntegerField(
        default=0, help_text='Timezone offset from UTC')

    def __str__(self):
        return '%s %s %s of %s' % (self.id, self.date, self.points,
                                   self.target_points)

    @classmethod
    def data_dict(cls, obj):
        result = {
            'id': obj.id,
            'date': obj.date.date(),
            'points': obj.points,
            'target_points': obj.targetPoints
        }
        # timeZoneOffset is not in the current API documentation, but I've
        # seen it before. I think we need to keep an eye out for it
        if hasattr(obj, 'timeZoneOffset') and obj.timeZoneOffset:
            result['time_zone_offset'] = obj.timeZoneOffset
        return result

    @classmethod
    def import_from_misfit(cls, misfit, uid, object_id=None):
        obj = misfit.goal(object_id=object_id)
        if not hasattr(obj, 'id'):
            return False, False
        data = cls.data_dict(obj)
        return cls.objects.update_or_create(
            user_id=uid, id=data['id'], defaults=data)

    @classmethod
    def import_all_from_misfit(cls, misfit, uid,
                               start_date=HISTORIC_START_DATE,
                               end_date=datetime.date.today()):
        # Keep track of the data we already have
        exists = cls.objects.filter(
            user_id=uid, date__gte=start_date, date__lte=end_date
        ).values_list('id', flat=True)
        obj_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            goals = misfit.goal(start_date=start, end_date=end)
            for goal in goals:
                if not hasattr(goal, 'id'):
                    # For some reason, goals occasionally have no id, ignore
                    continue
                if goal.id not in exists:
                    model_data = cls.data_dict(goal)
                    obj_list.append(cls(user_id=uid, **model_data))
        cls.objects.bulk_create(dedupe_by_field(obj_list, 'id'))


@python_2_unicode_compatible
class Session(MisfitModel):
    """
    A Misfit session:
    https://build.misfit.com/docs/cloudapi/api_references#session
    """
    ACTIVITY_TYPES = (('cycling', 'cycling'),
                      ('swimming', 'swimming'),
                      ('walking', 'walking'),
                      ('tennis', 'tennis'),
                      ('basketball', 'basketball'),
                      ('soccer', 'soccer'))

    id = models.CharField(
        max_length=MAX_KEY_LEN,
        primary_key=True,
        help_text='Session ID assigned by Misfit')
    user = models.ForeignKey(UserModel, help_text="The session's user")
    activity_type = models.CharField(
        choices=ACTIVITY_TYPES,
        max_length=15,
        help_text="The session's activity type, one of: {}".format(
            ', '.join([c for c, _ in ACTIVITY_TYPES])
        ))
    start_time = models.DateTimeField(help_text='Datetime the session started')
    duration = models.IntegerField(
        help_text='Length of the activity, in seconds')
    points = models.FloatField(
        null=True, help_text='Total points user gained for the activity')
    steps = models.IntegerField(
        null=True, help_text='Total steps user took for the activity')
    calories = models.FloatField(
        null=True, help_text='Total calories user burned for the activity')
    distance = models.FloatField(
        null=True,
        help_text='Total distance user covered for the activity, in miles')

    def __str__(self):
        return '%s %s %s' % (self.start_time, self.duration,
                             self.activity_type)

    @classmethod
    def data_dict(cls, obj):
        return {
            'id': obj.id,
            'activity_type': obj.activityType,
            'start_time': obj.startTime.datetime,
            'duration': obj.duration,
            'points': obj.points,
            'steps': obj.steps,
            'calories': obj.calories,
            'distance': obj.distance
        }

    @classmethod
    def import_from_misfit(cls, misfit, uid, object_id=None):
        data = cls.data_dict(misfit.session(object_id=object_id))
        return cls.objects.update_or_create(
            id=data['id'], user_id=uid, defaults=data)

    @classmethod
    def import_all_from_misfit(cls, misfit, uid,
                               start_date=HISTORIC_START_DATE,
                               end_date=datetime.date.today()):
        # Keep track of the data we already have
        exists = cls.objects.filter(
            user_id=uid,
            start_time__gte=start_date,
            start_time__lt=end_date + datetime.timedelta(days=1)
        ).values_list('id', flat=True)
        obj_list = []
        date_chunks = chunkify_dates(start_date, end_date, 30)
        for start, end in date_chunks:
            sessions = misfit.session(start_date=start, end_date=end)
            for session in sessions:
                if session.id not in exists:
                    model_data = cls.data_dict(session)
                    obj_list.append(cls(user_id=uid, **model_data))
        cls.objects.bulk_create(dedupe_by_field(obj_list, 'id'))


@python_2_unicode_compatible
class Sleep(MisfitModel):
    """
    A Misfit sleep session:
    https://build.misfit.com/docs/cloudapi/api_references#sleep
    """
    id = models.CharField(
        max_length=MAX_KEY_LEN,
        primary_key=True,
        help_text='The sleep ID assigned by Misfit')
    user = models.ForeignKey(UserModel, help_text="The sleep session's user")
    auto_detected = models.BooleanField(
        default=True, help_text='Was the sleep session auto-detected?')
    start_time = models.DateTimeField(
        help_text='Datetime the sleep session started')
    duration = models.IntegerField(
        help_text='Duration of the sleep session, in seconds')

    def __str__(self):
        return '%s %s' % (self.start_time, self.duration)

    @classmethod
    def data_dict(cls, obj):
        return {
            'id': obj.id,
            'auto_detected': obj.autoDetected,
            'start_time': obj.startTime.datetime,
            'duration': obj.duration
        }

    @classmethod
    def import_misfit_sleeps(cls, misfit, uid, sleeps):
        segments = {}
        for misfit_sleep in sleeps:
            data = cls.data_dict(misfit_sleep)
            sleep, created = cls.objects.update_or_create(
                id=data['id'], user_id=uid, defaults=data)
            segments[sleep.id] = misfit_sleep.data['sleepDetails']
            if not created:
                SleepSegment.objects.filter(sleep=sleep).delete()
        seg_list = []
        for sleep_id, segments in segments.items():
            for segment in segments:
                seg_list.append(SleepSegment(sleep_id=sleep_id,
                                             time=segment['datetime'],
                                             sleep_type=segment['value']))
        SleepSegment.objects.bulk_create(dedupe_by_field(seg_list, 'time'))

    @classmethod
    def import_from_misfit(cls, misfit, uid, object_id=None):
        cls.import_misfit_sleeps(
            misfit, uid, [misfit.sleep(object_id=object_id)])

    @classmethod
    def import_all_from_misfit(cls, misfit, uid,
                               start_date=HISTORIC_START_DATE,
                               end_date=datetime.date.today()):
        sleeps = []
        for start, end in chunkify_dates(start_date, end_date, 30):
            sleeps += misfit.sleep(start_date=start, end_date=end)
        cls.import_misfit_sleeps(misfit, uid, sleeps)


@python_2_unicode_compatible
class SleepSegment(models.Model):
    """
    A segment of sleep, part of a sleep session (Sleep)
    """
    AWAKE = 1
    SLEEP = 2
    DEEP_SLEEP = 3
    SLEEP_TYPES = (
        (AWAKE, 'awake'),
        (SLEEP, 'sleep'),
        (DEEP_SLEEP, 'deep sleep'),
    )

    sleep = models.ForeignKey(Sleep, help_text="The segment's sleep session")
    time = models.DateTimeField(help_text='The datetime of the segment')
    sleep_type = models.SmallIntegerField(
        choices=SLEEP_TYPES,
        help_text="The sleep segment's type, one of: {}".format(
            ', '.join(['{}({})'.format(ci, cs) for ci, cs in SLEEP_TYPES])
        ))

    def __str__(self):
        return '%s %s' % (self.time, self.sleep_type)

    class Meta:
        unique_together = ('sleep', 'time')
