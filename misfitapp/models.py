from django.conf import settings
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from math import pow

UserModel = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


@python_2_unicode_compatible
class MisfitUser(models.Model):
    user = models.ForeignKey(UserModel)
    misfit_user_id = models.CharField(max_length=24)
    access_token = models.TextField()
    last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if hasattr(self.user, 'get_username'):
            return self.user.get_username()
        else:  # Django 1.4
            return self.user.username


class Summary(models.Model):
    misfit_user = models.ForeignKey(MisfitUser)
    start_date = models.DateField()
    end_date = models.DateField()
    points = models.FloatField()
    steps = models.IntegerField()
    calories = models.FloatField()
    activity_calories = models.FloatField()
    distance = models.FloatField()
