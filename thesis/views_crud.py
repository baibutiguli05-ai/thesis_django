"""
Тақырыптар каталогы — класқа негізделген көріністер (CBV) арқылы толық CRUD:

    TopicListView    GET  /topics/                 тізім: іздеу, сүзу, сұрыптау, беттеу, агрегаттар
    TopicDetailView  GET  /topics/<pk>/            толық бет
    TopicCreateView  GET/POST /topics/new/         құру   (оқытушы, әкімші)
    TopicUpdateView  GET/POST /topics/<pk>/edit/   өңдеу  (иесі — студент алмаған болса, әкімші)
    TopicDeleteView  GET/POST /topics/<pk>/delete/ өшіру  (иесі — студент алмаған болса, әкімші)
    TeacherDetailView GET /teachers/<pk>/          оқытушының толық беті

N+1 болмауы үшін барлық сұраныстарда select_related / prefetch_related / annotate қолданылады.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Prefetch, Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import services as S
from .forms import TopicCrudForm
from .models import Tag, Teacher, Topic

SORTS = {
    'new': ('-created_at', 'Алдымен жаңалары'),
    'old': ('created_at', 'Алдымен ескілері'),
    'title': ('title', 'Атауы бойынша (А–Я)'),
    'popular': ('-app_count', 'Өтінімдер саны бойынша'),
    'teacher': ('teacher__full_name', 'Оқытушы бойынша'),
}


def visible_topics(user):
    """Рөлге қарай көрінетін тақырыптар."""
    qs = Topic.objects.all()
    role = S.role_of(user)
    if role == 'admin':
        return qs
    public = Q(proposed_by='teacher', status__in=['approved', 'taken'])
    if role == 'teacher':
        return qs.filter(public | Q(teacher__user=user))
    return qs.filter(public | Q(applications__student__user=user)).distinct()


def can_edit(user, topic):
    if user.is_staff:
        return True
    t = getattr(user, 'teacher', None)
    return t is not None and S.teacher_can_edit(topic, t)


class RoleContextMixin:
    """Бүйірлік мәзірдегі белгілер үшін (base.html) ортақ контекст."""
    active = 'catalog'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active'] = self.active
        role = S.role_of(self.request.user)
        if role == 'admin':
            ctx['counts'] = S.admin_counts()
        elif role == 'teacher':
            from .views import _teacher_counts
            ctx['counts'] = _teacher_counts(self.request.user.teacher)
        return ctx


# =====================================================================  READ

class TopicListView(LoginRequiredMixin, RoleContextMixin, ListView):
    template_name = 'topics/list.html'
    context_object_name = 'topics'
    paginate_by = 9

    def get_queryset(self):
        p = self.request.GET
        qs = (visible_topics(self.request.user)
              .select_related('teacher')                       # FK → бір JOIN
              .prefetch_related('tags')                        # M2M → бір қосымша сұраныс
              .annotate(app_count=Count('applications', distinct=True)))

        if p.get('q'):
            q = p['q'].strip()
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(teacher__full_name__icontains=q))
        if p.get('teacher', '').isdigit():
            qs = qs.filter(teacher_id=int(p['teacher']))
        if p.get('tag', '').isdigit():
            qs = qs.filter(tags__id=int(p['tag']))
        if p.get('status') in ('pending', 'approved', 'taken', 'rejected'):
            qs = qs.filter(status=p['status'])

        self.sort = p.get('sort') if p.get('sort') in SORTS else 'new'
        return qs.order_by(SORTS[self.sort][0], '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = visible_topics(self.request.user)
        # Агрегаттау: статустар бойынша санау — бір сұраныспен
        ctx['stats'] = base.aggregate(
            total=Count('id', distinct=True),
            approved=Count('id', filter=Q(status='approved'), distinct=True),
            taken=Count('id', filter=Q(status='taken'), distinct=True),
            pending=Count('id', filter=Q(status='pending'), distinct=True),
        )
        ctx['teachers'] = Teacher.objects.order_by('full_name').only('id', 'full_name')
        ctx['tags'] = (Tag.objects.annotate(n=Count('topics', filter=Q(topics__in=base), distinct=True))
                       .filter(n__gt=0).order_by('-n', 'name'))
        ctx['sorts'] = [(k, v[1]) for k, v in SORTS.items()]
        ctx['f'] = {k: self.request.GET.get(k, '') for k in ('q', 'teacher', 'tag', 'status')}
        ctx['f']['sort'] = self.sort
        qd = self.request.GET.copy()
        qd.pop('page', None)
        ctx['querystring'] = qd.urlencode()
        ctx['can_create'] = S.role_of(self.request.user) in ('teacher', 'admin')
        return ctx


class TopicDetailView(LoginRequiredMixin, RoleContextMixin, DetailView):
    template_name = 'topics/detail.html'
    context_object_name = 'topic'

    def get_queryset(self):
        return (visible_topics(self.request.user)
                .select_related('teacher', 'student', 'reviewed_by')
                .prefetch_related('tags'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        t = self.object
        ctx['app_stats'] = t.applications.aggregate(
            total=Count('id'),
            open=Count('id', filter=Q(teacher_status='pending') | Q(admin_status='pending')),
        )
        tag_ids = [tag.id for tag in t.tags.all()]
        ctx['similar'] = (visible_topics(self.request.user)
                          .exclude(pk=t.pk).filter(tags__in=tag_ids)
                          .annotate(shared=Count('tags', filter=Q(tags__in=tag_ids)))
                          .select_related('teacher').order_by('-shared', '-id')[:4]) if tag_ids else []
        ctx['can_edit'] = can_edit(self.request.user, t)
        return ctx


class TeacherDetailView(LoginRequiredMixin, RoleContextMixin, DetailView):
    template_name = 'topics/teacher_detail.html'
    context_object_name = 'teacher_obj'

    def get_queryset(self):
        public = Topic.objects.filter(proposed_by='teacher', status__in=['approved', 'taken']).prefetch_related('tags')
        return Teacher.objects.annotate(
            cs_taken_n=Count('students', filter=Q(students__major='CS'), distinct=True),
            students_n=Count('students', distinct=True),
        ).prefetch_related(Prefetch('topics', queryset=public, to_attr='public_topics'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        t = self.object
        ctx['cs_remaining'] = max(0, t.cs_quota - t.cs_taken_n)
        ctx['free_n'] = sum(1 for x in t.public_topics if x.status == 'approved')
        return ctx


# =====================================================================  CREATE / UPDATE / DELETE

class TeacherOrAdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return S.role_of(self.request.user) in ('teacher', 'admin')


class TopicFormMixin:
    form_class = TopicCrudForm
    template_name = 'topics/form.html'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['user'] = self.request.user
        return kw


class TopicCreateView(TeacherOrAdminMixin, RoleContextMixin, TopicFormMixin, CreateView):
    def form_valid(self, form):
        if not self.request.user.is_staff:
            form.instance.teacher = S.teacher_profile(self.request.user)
            form.instance.status = 'pending'
        form.instance.proposed_by = 'teacher'
        response = super().form_valid(form)
        messages.success(self.request, 'Тақырып құрылды.' if self.request.user.is_staff
                         else 'Тақырып құрылды және әкімшіге тексеруге жіберілді.')
        return response


class TopicUpdateView(TeacherOrAdminMixin, RoleContextMixin, TopicFormMixin, UpdateView):
    def get_queryset(self):
        return Topic.objects.select_related('teacher').prefetch_related('tags')

    def test_func(self):
        return super().test_func() and can_edit(self.request.user, self.get_object())

    def form_valid(self, form):
        if not self.request.user.is_staff:
            # Мазмұны өзгерген тақырып әкімшіге қайта тексеруге жіберіледі
            form.instance.status, form.instance.reviewed_at, form.instance.reviewed_by = 'pending', None, None
            form.instance.applications.filter(S.OPEN).update(admin_status='rejected', updated_at=timezone.now())
        response = super().form_valid(form)
        messages.success(self.request, 'Өзгерістер сақталды.' if self.request.user.is_staff
                         else 'Өзгерістер сақталды — тақырып әкімшіге қайта тексеруге жіберілді.')
        return response


class TopicDeleteView(TeacherOrAdminMixin, RoleContextMixin, DeleteView):
    template_name = 'topics/confirm_delete.html'
    context_object_name = 'topic'
    success_url = reverse_lazy('topic_list')

    def get_queryset(self):
        return Topic.objects.select_related('teacher', 'student').annotate(app_count=Count('applications'))

    def test_func(self):
        return super().test_func() and can_edit(self.request.user, self.get_object())

    def form_valid(self, form):
        messages.success(self.request, f'«{self.object.title}» тақырыбы өшірілді.')
        return super().form_valid(form)
