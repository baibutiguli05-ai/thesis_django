from django.urls import path

from . import views as v
from . import views_crud as crud

urlpatterns = [
    path('', v.home, name='home'),
    path('login/', v.login_view, name='login'),
    path('logout/', v.logout_view, name='logout'),
    path('register/', v.register_view, name='register'),
    path('files/<int:pk>/', v.download, name='download'),

    # Тақырыптар каталогы — CBV арқылы толық CRUD
    path('topics/', crud.TopicListView.as_view(), name='topic_list'),
    path('topics/new/', crud.TopicCreateView.as_view(), name='topic_create'),
    path('topics/<int:pk>/', crud.TopicDetailView.as_view(), name='topic_detail'),
    path('topics/<int:pk>/edit/', crud.TopicUpdateView.as_view(), name='topic_update'),
    path('topics/<int:pk>/delete/', crud.TopicDeleteView.as_view(), name='topic_delete'),
    path('teachers/<int:pk>/', crud.TeacherDetailView.as_view(), name='teacher_detail'),

    # Студент
    path('student/', v.student_home, name='student_home'),
    path('student/teachers/', v.student_teachers, name='student_teachers'),
    path('student/topics/', v.student_topics, name='student_topics'),
    path('student/progress/', v.student_progress, name='student_progress'),
    path('student/request-supervisor/', v.student_request_supervisor, name='student_request_supervisor'),
    path('student/apply-topic/', v.student_apply_topic, name='student_apply_topic'),
    path('student/propose-topic/', v.student_propose_topic, name='student_propose_topic'),
    path('student/upload/', v.student_upload, name='student_upload'),

    # Оқытушы
    path('teacher/', v.teacher_home, name='teacher_home'),
    path('teacher/topics/', v.teacher_topics, name='teacher_topics'),
    path('teacher/students/', v.teacher_students, name='teacher_students'),
    path('teacher/requests/<int:pk>/review/', v.teacher_review_request, name='teacher_review_request'),
    path('teacher/applications/<int:pk>/review/', v.teacher_review_application, name='teacher_review_application'),
    path('teacher/files/<int:pk>/comment/', v.teacher_comment, name='teacher_comment'),

    # Әкімші панелі
    path('panel/', v.panel, name='panel'),
    path('panel/requests/<int:pk>/review/', v.panel_review_request, name='panel_review_request'),
    path('panel/applications/<int:pk>/review/', v.panel_review_application, name='panel_review_application'),
    path('panel/topics/<int:pk>/review/', v.panel_review_topic, name='panel_review_topic'),
    path('panel/teachers/<int:pk>/quota/', v.panel_quota, name='panel_quota'),
    path('panel/t/<str:name>/', v.panel_table, name='panel_table'),
    path('panel/t/<str:name>/new/', v.panel_edit, name='panel_create'),
    path('panel/t/<str:name>/<int:pk>/edit/', v.panel_edit, name='panel_edit'),
    path('panel/t/<str:name>/<int:pk>/delete/', v.panel_delete, name='panel_delete'),
]
