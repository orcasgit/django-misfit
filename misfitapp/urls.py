from django.conf.urls import url

from . import views


urlpatterns = [
    # OAuth authentication
    url(r'^login/$', views.login, name='misfit-login'),
    url(r'^complete/$', views.complete, name='misfit-complete'),
    url(r'^error/$', views.error, name='misfit-error'),
    url(r'^logout/$', views.logout, name='misfit-logout'),

    # Misfit notifications
    url(r'^notification/$', views.notification, name='misfit-notification')
]
