# Your Misfit access credentials, which must be requested from Misfit.
# You must provide these in your project's settings.
MISFIT_CLIENT_ID = None
MISFIT_CLIENT_SECRET = None

# Where to redirect to after Misfit authentication is successfully completed.
MISFIT_LOGIN_REDIRECT = '/'

# Where to redirect to after Misfit authentication credentials have been
# removed.
MISFIT_LOGOUT_REDIRECT = '/'

# Where to redirect to if there is an error while authenticating a Misfit
# user.
MISFIT_ERROR_REDIRECT = None

# The template to use when an unavoidable error occurs during Misfit
# integration. This setting is ignored if MISFIT_ERROR_REDIRECT is set.
MISFIT_ERROR_TEMPLATE = 'misfit/error.html'

# The default message used by the misfit_integration_warning decorator to
# inform the user about Misfit integration. If a callable is given, it is
# called with the request as the only parameter to get the final value for the
# message.
MISFIT_DECORATOR_MESSAGE = 'This page requires Misfit integration.'
