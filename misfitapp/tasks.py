import arrow
import logging
import re
import sys

from celery import shared_task
from celery.exceptions import Reject
from cryptography.exceptions import InvalidSignature
from django.core.cache import cache
from misfit.exceptions import MisfitRateLimitError
from misfit.notification import MisfitNotification

from . import utils
from .models import MisfitUser, Profile, Device, Session, SleepSegment, Summary, Goal


logger = logging.getLogger(__name__)


def cc_to_underscore(name):
    """ Convert camelCase name to under_score """
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def cc_to_underscore_keys(dictionary):
    """ Convert dictionary keys from camelCase to under_score """
    return dict((cc_to_underscore(key), val) for key, val in dictionary.items())


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
            mfuser = MisfitUser.objects.filter(misfit_user_id=ownerId)
            if not mfuser.exists():
                logger.warning('Received a notification for a user who is not '
                               'in our database with id: %s' % ownerId)
                continue
            misfit = utils.create_misfit(access_token=mfuser[0].access_token)

            if message['type'] == 'profiles':
                process_profile(message, misfit)
            elif message['type'] == 'devices':
                process_device(message, misfit)
            elif message['type'] == 'sessions':
                process_session(message, misfit)
            elif message['type'] == 'sleeps':
                process_sleep(message, misfit)
            elif message['type'] == 'goals':
                process_goal(message, misfit)

                # Adjust date range for later summary retrieval
                goal = misfit.goal(object_id=message['id'])
                if not ownerId in date_ranges:
                    date_ranges[ownerId] = {'start_date': goal.date,
                                            'end_date': goal.date}
                elif goal.date < date_ranges[ownerId]['start_date']:
                    date_ranges[ownerId]['start_date'] = goal.date
                elif goal.date > date_ranges[ownerId]['end_date']:
                    date_ranges[ownerId]['end_date'] = goal.date


        # Use the date ranges we built to get summary data for each user
        for ownerId, date_range in date_ranges.items():
            mfusers = MisfitUser.objects.filter(misfit_user_id=ownerId)
            for mfuser in mfusers:
                misfit = utils.create_misfit(access_token=mfuser.access_token)
                summaries = misfit.summary(detail=True, **date_range)
                for summary in summaries:
                    summary_data = dict((cc_to_underscore(key), val)
                                        for key, val in summary.data.items())
                    existing_summ = Summary.objects.filter(
                        date=summary.date.datetime)
                    if existing_summ.exists():
                        existing_summ[0].update(**summary_data)
                    else:
                        summary_data['misfit_user'] = mfuser
                        Summary.objects.create(**summary_data)
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



def process_profile(message, misfit):
    if message['action'] == 'deleted':
        Profile.objects.filter(user_id=message['ownerId']).delete()
    elif message['action'] == 'created':
        data = cc_to_underscore_keys(misfit.profile().data)
        p = Profile(user_id=data.pop('user_id'), **data)
        p.save()
    elif message['action'] == 'updated':
        data = cc_to_underscore_keys(misfit.profile().data)
        Profile.objects.get_or_create(user_id=data.pop('user_id'), defaults=data)
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_device(message, misfit):
    if message['action'] == 'deleted':
        Device.objects.filter(pk=message['id']).delete()
    elif message['action'] == 'created':
        data = cc_to_underscore_keys(misfit.device().data)
        p = Device(pk=message['id'], user_id=message['ownerId'], **data)
        p.save()
    elif message['action'] == 'updated':
        data = cc_to_underscore_keys(misfit.device().data)
        Device.objects.get_or_create(pk=message['id'], user_id=message['ownerId'], defaults=data)
    else:
        raise Exception("Unknown message action: %s" % message['action'])


def process_session(message, misfit):
    pass

def process_sleep(message, misfit):
    pass

def process_goal(message, misfit):
    pass
 
