# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misfitapp', '0003_auto_20151009_1702'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_type',
            field=models.CharField(max_length=64, choices=[(b'shine', b'shine')]),
        ),
    ]
