from django import template

from misfitapp import utils


register = template.Library()


@register.filter
def is_integrated_with_misfit(user):
    """Returns ``True`` if we have OAuth info for the user.

    For example::

        {% if request.user|is_integrated_with_misfit %}
            do something
        {% else %}
            do something else
        {% endif %}
    """
    return utils.is_integrated(user)
