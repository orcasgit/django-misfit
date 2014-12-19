import arrow
import logging
import sys
import random

from celery import shared_task
from celery.exceptions import Reject
from cryptography.exceptions import InvalidSignature
from django.core.cache import cache
from datetime import timedelta, date
from misfit.exceptions import MisfitRateLimitError
from misfit.notification import MisfitNotification

from . import utils
from .models import (
    MisfitUser,
    Profile,
    Device,
    Session,
    Sleep,
    SleepSegment,
    Summary,
    Goal
)
from .extras import cc_to_underscore_keys, chunkify_dates

logger = logging.getLogger(__name__)


@shared_task
def import_historical(misfit_user):
    """
    Import a user's historical data from Misfit starting at start_date.
    Spin off a new task for each data type. If there is existing data,
    it is not overwritten.
    """
    for cls in (Profile, Device, Summary, Goal, Session, Sleep):
        import_historical_cls.delay(cls, misfit_user)


@shared_task
def import_historical_cls(cls, misfit_user):
    try:
        misfit = utils.create_misfit(access_token=misfit_user.access_token)
        cls.create_from_misfit(misfit, misfit_user.user_id)
    except MisfitRateLimitError:
        # We have hit the rate limit for the user, retry when it's reset,
        # according to the header in the reply from the failing API call
        headers = sys.exc_info()[1].response.headers
        reset = arrow.get(headers['x-ratelimit-reset'])
        retry_after_secs = (reset - arrow.now()).seconds + random.randrange(0, 5)
        logger.debug('Rate limit reached, will try again in %i seconds' %
                     retry_after_secs)
        raise process_notification.retry(e, countdown=retry_after_secs)
    except Exception:
        exc = sys.exc_info()[1]
        logger.exception("Unknown exception processing notification: %s" % exc)
        raise Reject(exc, requeue=False)


@shared_task
def process_notification(content):
    """ Process a Misfit notification """

    try:
        notification = MisfitNotification(content)
    except InvalidSignature:
        logger.exception('Invalid message signature')
        raise Reject('Invalid message signature', requeue=False)

    if notification.Type == 'SubscriptionConfirmation':
        # If the message is a subscription confirmation, then we are already
        # finished.
        return

    # For safety (so the queue doesn't crash) wrap all this in a big try/catch
    try:
        date_ranges = {}
        for message in notification.Message:
            ownerId = message['ownerId']
            try:
                mfuser = MisfitUser.objects.get(misfit_user_id=ownerId)
            except mfuser.DoesNotExist:
                logger.warning('Received a notification for a user who is not '
                               'in our database with id: %s' % ownerId)
                continue
            misfit = utils.create_misfit(access_token=mfuser.access_token)

            if message['type'] == 'profiles':
                process_profile(message, misfit, mfuser.user_id)
            elif message['type'] == 'devices':
                process_device(message, misfit, mfuser.user_id)
            elif message['type'] == 'sessions':
                process_session(message, misfit, mfuser.user_id)
            elif message['type'] == 'sleeps':
                process_sleep(message, misfit, mfuser.user_id)
            elif message['type'] == 'goals':
                goal = process_goal(message, misfit, mfuser.user_id)

                if goal:
                    # Adjust date range for later summary retrieval
                    # For whatever reason, the end_date is not inclusive, so
                    # we add a day
                    next_day = goal.date + arrow.util.timedelta(days=1)
                    if ownerId not in date_ranges:
                        date_ranges[ownerId] = {'start_date': goal.date,
                                                'end_date': next_day}
                    elif goal.date < date_ranges[ownerId]['start_date']:
                        date_ranges[ownerId]['start_date'] = goal.date
                    elif goal.date > date_ranges[ownerId]['end_date']:
                        date_ranges[ownerId]['end_date'] = next_day

        update_summaries(date_ranges)

    except MisfitRateLimitError:
        # We have hit the rate limit for the user, retry when it's reset,
        # according to the header in the reply from the failing API call
        headers = sys.exc_info()[1].response.headers
        reset = arrow.get(headers['x-ratelimit-reset'])
        retry_after_secs = (reset - arrow.now()).seconds
        logger.debug('Rate limit reached, will try again in %i seconds' %
                     retry_after_secs)
        raise process_notification.retry(e, countdown=retry_after_secs)
    except Exception:
        exc = sys.exc_info()[1]
        logger.exception("Unknown exception processing notification: %s" % exc)
        raise Reject(exc, requeue=False)


def process_device(message, misfit, uid):
    if message['action'] == 'deleted':
        Device.objects.filter(pk=message['id']).delete()
    elif message['action'] == 'created' or message['action'] == 'updated':
        device = misfit.device()
        data = cc_to_underscore_keys(device.data)
        d, created = Device.objects.get_or_create(user_id=uid, defaults=data)
        if not created:
            for attr, val in data.items():
                setattr(d, attr, val)
            d.save()
        return device
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_goal(message, misfit, uid):
    if message['action'] == 'deleted':
        Goal.objects.filter(pk=message['id']).delete()
    elif message['action'] == 'created' or message['action'] == 'updated':
        goal = misfit.goal(object_id=message['id'])
        data = cc_to_underscore_keys(goal.data)
        data['user_id'] = uid
        d, created = Goal.objects.get_or_create(pk=message['id'],
                                                defaults=data)
        if not created:
            for attr, val in data.items():
                setattr(d, attr, val)
            d.save()
        return goal
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_profile(message, misfit, uid):
    if message['action'] == 'deleted':
        Profile.objects.filter(user_id=uid).delete()
    elif message['action'] == 'created' or message['action'] == 'updated':
        profile = misfit.profile()
        data = cc_to_underscore_keys(profile.data)
        data.pop('user_id')
        p, created = Profile.objects.get_or_create(user_id=uid, defaults=data)
        if not created:
            for attr, val in data.items():
                setattr(p, attr, val)
            p.save()
        return profile
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_session(message, misfit, uid):
    if message['action'] == 'deleted':
        Session.objects.filter(pk=message['id']).delete()
    elif message['action'] == 'created' or message['action'] == 'updated':
        session = misfit.session(object_id=message['id'])
        data = cc_to_underscore_keys(session.data)
        data['user_id'] = uid
        s, created = Session.objects.get_or_create(id=message['id'],
                                                   defaults=data)
        if not created:
            for attr, val in data.items():
                setattr(s, attr, val)
            s.save()
        return session
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_sleep(message, misfit, uid):
    if message['action'] == 'deleted':
        Sleep.objects.filter(pk=message['id']).delete()
    elif message['action'] == 'created' or message['action'] == 'updated':
        sleep = misfit.sleep(object_id=message['id'])
        data = cc_to_underscore_keys(sleep.data)
        data['user_id'] = uid
        segments = data.pop('sleep_details')
        s, created = Sleep.objects.get_or_create(id=message['id'],
                                                 defaults=data)
        if not created:
            for attr, val in data.items():
                setattr(s, attr, val)
            s.save()
            # For simplicity, remove existing segments on updates,
            # then save the complete list
            SleepSegment.objects.filter(sleep=s).delete()
        seg_list = []
        for seg in segments:
            seg_list.append(SleepSegment(sleep=s,
                                         time=seg['datetime'],
                                         sleep_type=seg['value']))
        SleepSegment.objects.bulk_create(seg_list)
        return sleep
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def update_summaries(date_ranges):
    """ Use the date ranges we built to get summary data for each user. """
    for ownerId, date_range in date_ranges.items():
        try:
            mfuser = MisfitUser.objects.get(misfit_user_id=ownerId)
        except MisfitUser.DoesNotExist:
            logger.warning('Count not find Misfit user %s' % ownderId)
            continue

        misfit = utils.create_misfit(access_token=mfuser.access_token)

        for start, end in chunkify_dates(date_range['start_date'], date_range['end_date']):
            summaries = misfit.summary(detail=True, start_date=start, end_date=end)
            for summary in summaries:
                data = cc_to_underscore_keys(summary.data)
                s, created = Summary.objects.get_or_create(user_id=mfuser.user_id,
                                                           date=data['date'],
                                                           defaults=data)
                if not created:
                    for attr, val in data.items():
                        setattr(s, attr, val)
                    s.save()
