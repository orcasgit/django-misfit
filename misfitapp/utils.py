from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from misfit.auth import MisfitAuth
from misfit import Misfit

from . import defaults
from .models import MisfitUser


def create_misfit(access_token, client_id=None, client_secret=None, **kwargs):
    """ Shortcut to create a Misfit instance. """

    client_key, client_secret = get_client_id_and_secret(
        client_id=client_id, client_secret=client_secret)
    return Misfit(client_key, client_secret, access_token, **kwargs)


def create_misfit_auth(**kwargs):
    return MisfitAuth(*get_client_id_and_secret(), **kwargs)


def get_client_id_and_secret(client_id=None, client_secret=None):
    """
    If client_id or client_secret are not provided, then the values
    specified in settings are used.
    """
    if client_id is None:
        client_id = get_setting('MISFIT_CLIENT_ID')
    if client_secret is None:
        client_secret = get_setting('MISFIT_CLIENT_SECRET')

    if client_id is None or client_secret is None:
        raise ImproperlyConfigured(
            "Client key and client secret cannot be null, and must be "
            "explicitly specified or set in your Django settings")

    return (client_id, client_secret)

def is_integrated(user):
    """Returns ``True`` if we have OAuth info for the user.

    This does not require that the access token is valid.

    :param user: A Django User.
    """
    if user.is_authenticated() and user.is_active:
        return MisfitUser.objects.filter(user=user).exists()
    return False


def get_setting(name, use_defaults=True):
    """Retrieves the specified setting from the settings file.

    If the setting is not found and use_defaults is True, then the default
    value specified in defaults.py is used. Otherwise, we raise an
    ImproperlyConfigured exception for the setting.
    """
    if hasattr(settings, name):
        return getattr(settings, name)
    if use_defaults:
        if hasattr(defaults, name):
            return getattr(defaults, name)
    msg = "{0} must be specified in your settings".format(name)
    raise ImproperlyConfigured(msg)
