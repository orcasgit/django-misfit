# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.CharField(max_length=24, serialize=False, primary_key=True)),
                ('device_type', models.CharField(max_length=5, choices=[(b'shine', b'shine')])),
                ('serial_number', models.CharField(max_length=100)),
                ('firmware_version', models.CharField(max_length=100)),
                ('battery_level', models.SmallIntegerField()),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Goal',
            fields=[
                ('id', models.CharField(max_length=24, serialize=False, primary_key=True)),
                ('date', models.DateField()),
                ('points', models.FloatField()),
                ('target_points', models.IntegerField()),
                ('time_zone_offset', models.SmallIntegerField(default=0)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MisfitUser',
            fields=[
                ('misfit_user_id', models.CharField(max_length=24, serialize=False, primary_key=True)),
                ('access_token', models.TextField()),
                ('last_update', models.DateTimeField(null=True, blank=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('email', models.EmailField(max_length=254)),
                ('birthday', models.DateField()),
                ('gender', models.CharField(max_length=6, choices=[(b'male', b'male'), (b'female', b'female')])),
                ('name', models.TextField()),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Session',
            fields=[
                ('id', models.CharField(max_length=24, serialize=False, primary_key=True)),
                ('activity_type', models.CharField(max_length=15, choices=[(b'cycling', b'cycling'), (b'swimming', b'swimming'), (b'walking', b'walking'), (b'tennis', b'tennis'), (b'basketball', b'basketball'), (b'soccer', b'soccer')])),
                ('start_time', models.DateTimeField()),
                ('duration', models.IntegerField()),
                ('points', models.FloatField(null=True)),
                ('steps', models.IntegerField(null=True)),
                ('calories', models.FloatField(null=True)),
                ('distance', models.FloatField(null=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Sleep',
            fields=[
                ('id', models.CharField(max_length=24, serialize=False, primary_key=True)),
                ('auto_detected', models.BooleanField(default=True)),
                ('start_time', models.DateTimeField()),
                ('duration', models.IntegerField()),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SleepSegment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time', models.DateTimeField()),
                ('sleep_type', models.SmallIntegerField(choices=[(1, b'awake'), (2, b'sleep'), (3, b'deep sleep')])),
                ('sleep', models.ForeignKey(to='misfitapp.Sleep')),
            ],
        ),
        migrations.CreateModel(
            name='Summary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('points', models.FloatField()),
                ('steps', models.IntegerField()),
                ('calories', models.FloatField()),
                ('activity_calories', models.FloatField()),
                ('distance', models.FloatField()),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='summary',
            unique_together=set([('user', 'date')]),
        ),
        migrations.AlterUniqueTogether(
            name='sleepsegment',
            unique_together=set([('sleep', 'time')]),
        ),
        migrations.AlterUniqueTogether(
            name='sleep',
            unique_together=set([('user', 'start_time')]),
        ),
        migrations.AlterUniqueTogether(
            name='session',
            unique_together=set([('user', 'start_time')]),
        ),
        migrations.AlterUniqueTogether(
            name='goal',
            unique_together=set([('user', 'date')]),
        ),
    ]
