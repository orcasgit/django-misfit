from django.conf.urls import patterns, url

from . import views


urlpatterns = patterns(
    '',

    # OAuth authentication
    url(r'^login/$', views.login, name='misfit-login'),
    url(r'^complete/$', views.complete, name='misfit-complete'),
    url(r'^error/$', views.error, name='misfit-error'),
    url(r'^logout/$', views.logout, name='misfit-logout')
)
