# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('misfitapp', '0002_auto_20151008_1530'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='email',
            field=models.EmailField(max_length=254, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='name',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='goal',
            unique_together=set([]),
        ),
        migrations.AlterUniqueTogether(
            name='session',
            unique_together=set([]),
        ),
    ]
