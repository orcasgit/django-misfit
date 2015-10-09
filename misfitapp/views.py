import json

from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.dispatch import receiver
from django.http import HttpResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from misfit.notification import MisfitNotification

from . import utils
from .models import MisfitUser
from .tasks import process_notification, import_historical


@login_required
def login(request):
    """
    Begins the OAuth authentication process by redirecting the user to the
    Misfit site for authorization.

    When the user has finished at the Misfit site, they will be redirected
    to the :py:func:`misfitapp.views.complete` view.

    If 'next' is provided in the GET data, it is saved in the session so the
    :py:func:`misfitapp.views.complete` view can redirect the user to that
    URL upon successful authentication.

    URL name:
        `misfit-login`
    """
    next_url = request.GET.get('next', None)
    if next_url:
        request.session['misfit_next'] = next_url
    else:
        request.session.pop('misfit_next', None)

    redirect_uri = request.build_absolute_uri(reverse('misfit-complete'))
    auth = utils.create_misfit_auth(redirect_uri=redirect_uri)
    auth_url = auth.authorize_url()
    request.session['state'] = auth.state
    return redirect(auth_url)


@login_required
def complete(request):
    """
    After the user authorizes us, Misfit sends a callback to this URL to
    complete authentication.

    If there was an error, the user is redirected to the url set in
    :ref:`MISFIT_ERROR_REDIRECT` if it is set, or to the `error` view
    otherwise.

    If the authorization was successful, the credentials are stored for us to
    use later, and the user is redirected. If 'next_url' is in the request
    session, the user is redirected to that URL. Otherwise, they are
    redirected to the URL specified by the setting
    :ref:`MISFIT_LOGIN_REDIRECT`.

    URL name:
        `misfit-complete`
    """
    try:
        redirect_uri = request.build_absolute_uri(reverse('misfit-complete'))
        auth = utils.create_misfit_auth(state=request.session['state'],
                                        redirect_uri=redirect_uri)
        del request.session['state']
        access_token = auth.fetch_token(request.GET['code'],
                                        request.GET['state'])
        misfit = utils.create_misfit(access_token)
        profile = misfit.profile()
    except:
        next_url = utils.get_setting('MISFIT_ERROR_REDIRECT') or reverse('misfit-error')
        return redirect(next_url)

    user_updates = {'access_token': access_token,
                    'misfit_user_id': profile.userId}
    misfit_user = MisfitUser.objects.filter(user=request.user)
    if misfit_user.exists():
        misfit_user.update(**user_updates)
        misfit_user = misfit_user[0]
    else:
        user_updates['user'] = request.user
        misfit_user = MisfitUser.objects.create(**user_updates)
    # Add the Misfit user info to the session
    request.session['misfit_profile'] = profile.data

    # Import their data
    import_historical.delay(misfit_user)

    next_url = request.session.pop('misfit_next', None) or utils.get_setting(
        'MISFIT_LOGIN_REDIRECT')
    return redirect(next_url)


@receiver(user_logged_in)
def create_misfit_session(sender, request, user, **kwargs):
    """ If the user is a Misfit user, update the profile in the session. """

    if (user.is_authenticated() and utils.is_integrated(user) and
            user.is_active):
        misfit_user = MisfitUser.objects.filter(user=user)
        if misfit_user.exists():
            api = utils.create_misfit(misfit_user[0].access_token)
            try:
                request.session['misfit_profile'] = api.profile().data
            except:
                pass


@login_required
def error(request):
    """
    The user is redirected to this view if we encounter an error acquiring
    their Misfit credentials. It renders the template defined in the setting
    :ref:`MISFIT_ERROR_TEMPLATE`. The default template, located at
    *misfit/error.html*, simply informs the user of the error::

        <html>
            <head>
                <title>Misfit Authentication Error</title>
            </head>
            <body>
                <h1>Misfit Authentication Error</h1>

                <p>
                    We encontered an error while attempting to authenticate you
                    through Misfit.
                </p>
            </body>
        </html>

    URL name:
        `misfit-error`
    """
    return render(request, utils.get_setting('MISFIT_ERROR_TEMPLATE'), {})


@login_required
def logout(request):
    """Forget this user's Misfit credentials.

    If the request has a `next` parameter, the user is redirected to that URL.
    Otherwise, they're redirected to the URL defined in the setting
    :ref:`MISFIT_LOGOUT_REDIRECT`.

    URL name:
        `misfit-logout`
    """
    misfit_user = MisfitUser.objects.filter(user=request.user)
    misfit_user.delete()
    next_url = request.GET.get('next', None) or utils.get_setting(
        'MISFIT_LOGOUT_REDIRECT')
    return redirect(next_url)


@csrf_exempt
@require_POST
def notification(request):
    process_notification.delay(request.body)
    return HttpResponse()
