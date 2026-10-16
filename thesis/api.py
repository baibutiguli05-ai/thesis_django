"""
REST API (Django REST Framework).

  GET/POST           /api/teachers/                      — жетекшілер (CS квотасы, тақырыптар саны)
  GET/PUT/PATCH/DEL  /api/teachers/{id}/                 — (өзгерту/өшіру — тек әкімші)
  GET/POST           /api/topics/                        — тақырыптар  (?teacher=1&status=approved)
  GET/PUT/PATCH/DEL  /api/topics/{id}/
  POST               /api/topics/{id}/review/            — әкімші: {"decision": "approved" | "rejected"}
  GET/POST           /api/students/                      — студенттер (әкімші — барлығы, оқытушы — өз студенттері)
  GET/POST           /api/supervisor-requests/           — студент: {"teacher": 1, "message": "..."}
  POST               /api/supervisor-requests/{id}/review/
  GET/POST           /api/applications/                  — студент: {"topic": 3}
  POST               /api/applications/propose/          — студент: {"title": "...", "description": "..."}
  POST               /api/applications/{id}/review/
  GET/POST           /api/progress-files/                — студент: multipart {title, note, file}
  POST               /api/progress-files/{id}/comment/   — оқытушы: {"comment": "..."}
  GET                /api/me/                            — ағымдағы пайдаланушы
"""
from django.db.models import Count, Q
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import services as S
from .models import Application, ProgressFile, Student, SupervisorRequest, Teacher, Topic
from .views import UPLOAD_EXT, UPLOAD_MAX


# ============================================================ рұқсаттар

class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or request.user.is_staff


def _service(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except S.ServiceError as e:
        raise ValidationError({'detail': str(e)})


def _decision(request):
    d = request.data.get('decision')
    if d not in ('approved', 'rejected'):
        raise ValidationError({'decision': 'Мәні "approved" немесе "rejected" болуы керек.'})
    return d


# ============================================================ сериализаторлар

class TeacherSerializer(serializers.ModelSerializer):
    # Мәндер queryset-тегі annotate()-тен алынады (N+1 жоқ)
    cs_taken = serializers.IntegerField(source='cs_taken_n', read_only=True)
    cs_remaining = serializers.SerializerMethodField()
    topics_count = serializers.IntegerField(source='topics_n', read_only=True)

    class Meta:
        model = Teacher
        fields = ['id', 'full_name', 'academic_title', 'department', 'research_area', 'email',
                  'cs_quota', 'cs_taken', 'cs_remaining', 'topics_count', 'user']

    def get_cs_remaining(self, obj):
        taken = getattr(obj, 'cs_taken_n', None)
        return max(0, obj.cs_quota - (obj.cs_taken if taken is None else taken))


def teachers_annotated():
    return Teacher.objects.annotate(
        cs_taken_n=Count('students', filter=Q(students__major='CS'), distinct=True),
        topics_n=Count('topics', filter=Q(topics__proposed_by='teacher', topics__status__in=['approved', 'taken']), distinct=True),
    ).order_by('full_name')


class TopicSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)

    class Meta:
        model = Topic
        fields = ['id', 'title', 'description', 'teacher', 'teacher_name', 'proposed_by', 'status', 'reviewed_at', 'created_at']
        read_only_fields = ['proposed_by', 'reviewed_at', 'created_at']

    def get_fields(self):
        fields = super().get_fields()
        user = self.context['request'].user
        if not user.is_staff:
            # Оқытушы тақырыптың статусын / иесін өзгерте алмайды
            fields['status'].read_only = True
            fields['teacher'].read_only = True
        return fields


class StudentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True, default=None)
    topic_title = serializers.CharField(source='topic.title', read_only=True, default=None)

    class Meta:
        model = Student
        fields = ['id', 'full_name', 'group_name', 'major', 'teacher', 'teacher_name', 'topic', 'topic_title', 'user']


class TwoStepSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)


class SupervisorRequestSerializer(TwoStepSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)

    class Meta:
        model = SupervisorRequest
        fields = ['id', 'student', 'student_name', 'teacher', 'teacher_name', 'message',
                  'teacher_status', 'admin_status', 'status', 'created_at', 'updated_at']
        read_only_fields = ['student', 'teacher_status', 'admin_status', 'created_at', 'updated_at']


class ApplicationSerializer(TwoStepSerializer):
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    proposed_by = serializers.CharField(source='topic.proposed_by', read_only=True)

    class Meta:
        model = Application
        fields = ['id', 'student', 'student_name', 'topic', 'topic_title', 'proposed_by',
                  'teacher_status', 'admin_status', 'status', 'created_at', 'updated_at']
        read_only_fields = ['student', 'teacher_status', 'admin_status', 'created_at', 'updated_at']


class ProgressFileSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)

    class Meta:
        model = ProgressFile
        fields = ['id', 'student', 'student_name', 'topic', 'title', 'note', 'file', 'original_name',
                  'teacher_comment', 'commented_at', 'created_at']
        read_only_fields = ['student', 'topic', 'original_name', 'teacher_comment', 'commented_at', 'created_at']

    def validate_file(self, f):
        if f.size > UPLOAD_MAX:
            raise serializers.ValidationError('Файл 20 MB-тан аспауы керек.')
        if f.name.rsplit('.', 1)[-1].lower() not in UPLOAD_EXT:
            raise serializers.ValidationError('Бұл файл түріне рұқсат жоқ.')
        return f


# ============================================================ viewset-тер

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = teachers_annotated()
    serializer_class = TeacherSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]


class TopicViewSet(viewsets.ModelViewSet):
    serializer_class = TopicSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Topic.objects.select_related('teacher').prefetch_related('tags')
        role = S.role_of(u)
        if role == 'student':
            # Студент: бекітілген тақырыптар + өзі ұсынған тақырыптар
            qs = qs.filter(Q(proposed_by='teacher', status__in=['approved', 'taken']) | Q(applications__student__user=u)).distinct()
        elif role == 'teacher':
            qs = qs.filter(Q(teacher=u.teacher) | Q(proposed_by='teacher', status__in=['approved', 'taken'])).distinct()
        for p in ('teacher', 'status', 'proposed_by'):
            if self.request.query_params.get(p):
                qs = qs.filter(**{p: self.request.query_params[p]})
        return qs

    def perform_create(self, serializer):
        u = self.request.user
        if u.is_staff:
            serializer.save(proposed_by='teacher')
        elif S.role_of(u) == 'teacher':
            serializer.save(teacher=u.teacher, proposed_by='teacher', status='pending')
        else:
            raise PermissionDenied('Студент тақырыпты /api/applications/propose/ арқылы ұсынады.')

    def perform_update(self, serializer):
        u, topic = self.request.user, serializer.instance
        if u.is_staff:
            serializer.save()
        elif S.role_of(u) == 'teacher' and S.teacher_can_edit(topic, u.teacher):
            d = serializer.validated_data
            _service(S.update_teacher_topic, topic, u.teacher, d.get('title', topic.title), d.get('description', topic.description))
        else:
            raise PermissionDenied('Бұл тақырыпты өзгерту мүмкін емес.')

    def perform_destroy(self, topic):
        u = self.request.user
        if u.is_staff:
            topic.delete()
        elif S.role_of(u) == 'teacher':
            _service(S.delete_teacher_topic, topic, u.teacher)
        else:
            raise PermissionDenied()

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied('Тек әкімші.')
        msg = _service(S.admin_review_topic, pk, _decision(request), request.user)
        return Response({'detail': msg, 'topic': TopicSerializer(Topic.objects.get(pk=pk), context={'request': request}).data})


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        u = self.request.user
        qs = Student.objects.select_related('teacher', 'topic')
        role = S.role_of(u)
        if role == 'teacher':
            return qs.filter(teacher=u.teacher)
        if role == 'student':
            return qs.filter(user=u)
        return qs


class _TwoStepViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.DestroyModelMixin, viewsets.GenericViewSet):
    model = None
    related = ('student',)
    review_fn = None
    teacher_filter = None

    def get_queryset(self):
        u = self.request.user
        qs = self.model.objects.select_related(*self.related).order_by('-id')
        role = S.role_of(u)
        if role == 'student':
            return qs.filter(student__user=u)
        if role == 'teacher':
            return qs.filter(**{self.teacher_filter: u.teacher})
        return qs

    def perform_destroy(self, obj):
        if not self.request.user.is_staff:
            raise PermissionDenied('Тек әкімші өшіре алады.')
        obj.delete()

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        role = S.role_of(request.user)
        if role not in ('teacher', 'admin'):
            raise PermissionDenied('Тек оқытушы немесе әкімші.')
        teacher = request.user.teacher if role == 'teacher' else None
        msg = _service(type(self).review_fn, int(pk), role, _decision(request), teacher)
        obj = self.model.objects.get(pk=pk)
        return Response({'detail': msg, 'data': self.get_serializer(obj).data})


class SupervisorRequestViewSet(_TwoStepViewSet):
    model = SupervisorRequest
    related = ('student', 'teacher')
    serializer_class = SupervisorRequestSerializer
    review_fn = staticmethod(S.review_supervisor_request)
    teacher_filter = 'teacher'

    def create(self, request, *args, **kwargs):
        if S.role_of(request.user) != 'student':
            raise PermissionDenied('Өтінімді тек студент жібереді.')
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = _service(S.request_supervisor, S.student_profile(request.user),
                       ser.validated_data['teacher'], ser.validated_data.get('message', ''))
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)


class ApplicationViewSet(_TwoStepViewSet):
    model = Application
    related = ('student', 'topic')
    serializer_class = ApplicationSerializer
    review_fn = staticmethod(S.review_application)
    teacher_filter = 'topic__teacher'

    def create(self, request, *args, **kwargs):
        if S.role_of(request.user) != 'student':
            raise PermissionDenied('Өтінімді тек студент жібереді.')
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = _service(S.apply_for_topic, S.student_profile(request.user), ser.validated_data['topic'])
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def propose(self, request):
        if S.role_of(request.user) != 'student':
            raise PermissionDenied('Тек студент.')
        obj = _service(S.propose_own_topic, S.student_profile(request.user),
                       request.data.get('title'), request.data.get('description', ''))
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)


class ProgressFileViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = ProgressFileSerializer

    def get_queryset(self):
        u = self.request.user
        qs = ProgressFile.objects.select_related('student')
        role = S.role_of(u)
        if role == 'student':
            return qs.filter(student__user=u)
        if role == 'teacher':
            return qs.filter(student__teacher=u.teacher)
        return qs

    def perform_create(self, serializer):
        if S.role_of(self.request.user) != 'student':
            raise PermissionDenied('Файлды тек студент жүктейді.')
        s = S.student_profile(self.request.user)
        if not s.topic_id:
            raise ValidationError({'detail': 'Файл жүктеу үшін тақырыбыңыз ресми бекітілуі керек.'})
        f = serializer.validated_data.get('file')
        serializer.save(student=s, topic_id=s.topic_id, original_name=f.name[:255] if f else '')

    def perform_destroy(self, obj):
        u = self.request.user
        if not (u.is_staff or obj.student.user_id == u.id):
            raise PermissionDenied()
        obj.delete()

    @action(detail=True, methods=['post'])
    def comment(self, request, pk=None):
        if S.role_of(request.user) != 'teacher':
            raise PermissionDenied('Тек жетекші.')
        msg = _service(S.comment_progress, pk, request.user.teacher, request.data.get('comment', ''))
        return Response({'detail': msg, 'data': self.get_serializer(ProgressFile.objects.get(pk=pk)).data})


@api_view(['GET'])
def me(request):
    u = request.user
    role = S.role_of(u)
    data = {'id': u.id, 'username': u.username, 'role': role}
    if role == 'student':
        data['student'] = StudentSerializer(S.student_profile(u), context={'request': request}).data
    elif role == 'teacher':
        data['teacher'] = TeacherSerializer(teachers_annotated().get(pk=u.teacher.pk), context={'request': request}).data
    return Response(data)
