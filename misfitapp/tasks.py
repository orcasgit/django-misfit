import arrow
import logging
import sys

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

logger = logging.getLogger(__name__)


def misfit_retry_exc(task_func, exc):
    # We have hit the rate limit for the user, retry when it's reset,
    # according to the header in the reply from the failing API call
    reset = arrow.get(exc.response.headers['x-ratelimit-reset'])
    secs = (reset - arrow.now()).seconds
    logger.debug('Rate limit reached, will try again in %i seconds' % secs)
    return task_func.retry(countdown=secs)


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
        cls.import_all_from_misfit(misfit, misfit_user.user_id)
    except MisfitRateLimitError:
        raise misfit_retry_exc(import_historical_cls, sys.exc_info()[1])
    except Exception:
        exc = sys.exc_info()[1]
        logger.exception("Unknown exception importing data: %s" % exc)
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
        summaries = {}
        for message in notification.Message:
            ownerId = message.ownerId
            try:
                mfuser = MisfitUser.objects.get(misfit_user_id=ownerId)
            except MisfitUser.DoesNotExist:
                logger.warning('Received a notification for a user who is not '
                               'in our database with id: %s' % ownerId)
                continue
            misfit = utils.create_misfit(access_token=mfuser.access_token)

            uid = mfuser.user_id
            if message.type == 'profiles':
                Profile.process_message(message, misfit, uid)
            elif message.type == 'devices':
                Device.process_message(message, misfit, uid)
            elif message.type == 'sessions':
                Session.process_message(message, misfit, uid)
            elif message.type == 'sleeps':
                Sleep.process_message(message, misfit, uid)
            elif message.type == 'goals':
                goal, created = Goal.process_message(message, misfit, uid)

                if goal:
                    # Adjust date range for later summary retrieval
                    # For whatever reason, the end_date is not inclusive, so
                    # we add a day
                    next_day = goal.date + arrow.util.timedelta(days=1)
                    if ownerId not in summaries:
                        summaries[ownerId] = {
                            'misfit': misfit,
                            'mfuser_id': mfuser.user_id,
                            'date_range': {'start': goal.date, 'end': next_day}
                        }
                    elif goal.date < summaries[ownerId]['date_range']['start']:
                        summaries[ownerId]['date_range']['start'] = goal.date
                    elif goal.date > summaries[ownerId]['date_range']['end']:
                        summaries[ownerId]['date_range']['end'] = next_day

        # Use the date ranges we built to get updated summary data
        for ownerId, summary in summaries.items():
            Summary.import_from_misfit(
                summary['misfit'], summary['mfuser_id'], update=True,
                start_date=summary['date_range']['start'],
                end_date=summary['date_range']['end'])

    except MisfitRateLimitError:
        raise misfit_retry_exc(process_notification, sys.exc_info()[1])
    except Exception:
        exc = sys.exc_info()[1]
        logger.exception("Unknown exception processing notification: %s" % exc)
        raise Reject(exc, requeue=False)
