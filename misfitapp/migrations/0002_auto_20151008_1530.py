# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('misfitapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='last_sync_time',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='avatar',
            field=models.URLField(null=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='sleep',
            unique_together=set([]),
        ),
    ]
