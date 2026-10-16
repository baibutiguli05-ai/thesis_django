from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register('teachers', api.TeacherViewSet, basename='api-teacher')
router.register('topics', api.TopicViewSet, basename='api-topic')
router.register('students', api.StudentViewSet, basename='api-student')
router.register('supervisor-requests', api.SupervisorRequestViewSet, basename='api-supervisor-request')
router.register('applications', api.ApplicationViewSet, basename='api-application')
router.register('progress-files', api.ProgressFileViewSet, basename='api-progress-file')

urlpatterns = [
    path('me/', api.me, name='api-me'),
    path('', include(router.urls)),
]
