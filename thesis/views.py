import os

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services as S
from .decorators import role_required
from .forms import RegisterForm, StudentForm, TeacherForm, TopicForm
from .models import Application, ProgressFile, Student, SupervisorRequest, Teacher, Topic

UPLOAD_EXT = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'zip', 'rar', '7z', 'png', 'jpg', 'jpeg', 'ipynb', 'py'}
UPLOAD_MAX = 20 * 1024 * 1024


def run(request, fn, *args, **kwargs):
    """Сервис функциясын орындап, нәтижесін хабарлама ретінде көрсетеді."""
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, str):
            messages.success(request, result)
        return True
    except S.ServiceError as e:
        messages.error(request, str(e))
        return False


# =====================================================================  Auth

def home(request):
    role = S.role_of(request.user)
    if role == 'admin':
        return redirect('panel')
    if role == 'teacher':
        return redirect('teacher_home')
    if role == 'student':
        return redirect('student_home')
    return redirect('login')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = ''
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username', '').strip(),
                            password=request.POST.get('password', ''))
        if user:
            login(request, user)
            return redirect(request.GET.get('next') or 'home')
        error = 'Логин немесе құпия сөз қате!'
    return render(request, 'auth/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')


@transaction.atomic
def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(username=d['username'], password=d['password'], first_name=d['full_name'][:150])
        if d['role'] == 'teacher':
            Teacher.objects.create(user=user, full_name=d['full_name'])
        else:
            Student.objects.create(user=user, full_name=d['full_name'])
        messages.success(request, 'Тіркелу сәтті өтті! Жүйеге кіріңіз.')
        return redirect('login')
    return render(request, 'auth/register.html', {'form': form})


def download(request, pk):
    if not request.user.is_authenticated:
        return redirect('login')
    f = get_object_or_404(ProgressFile.objects.select_related('student'), pk=pk)
    if not f.file or not S.file_visible_to(request.user, f):
        raise Http404
    try:
        return FileResponse(f.file.open('rb'), filename=f.original_name or os.path.basename(f.file.name))
    except FileNotFoundError:
        raise Http404


# =====================================================================  Student

def _student_ctx(request):
    s = S.student_profile(request.user)
    req = s.supervisor_requests.select_related('teacher').first()
    app = s.applications.select_related('topic').first()
    return s, {'student': s, 'teacher': s.teacher, 'topic': s.topic, 'sup_request': req, 'application': app}


@role_required('student')
def student_home(request):
    s, ctx = _student_ctx(request)
    files = list(s.files.all())
    teacher, req, app = ctx['teacher'], ctx['sup_request'], ctx['application']

    sup_state = 'done' if teacher else ('pending' if req and req.status == 'pending' else 'todo')
    top_state = 'done' if s.topic else ('locked' if not teacher else ('pending' if app and app.status == 'pending' else 'todo'))
    pro_state = ('done' if files else 'todo') if s.topic else 'locked'

    if sup_state == 'todo':
        nxt = ('Ғылыми жетекшіні таңдаңыз', 'Жетекшілер тізімінен бос орны бар оқытушыны таңдап, өтінім жіберіңіз.', 'student_teachers', 'Жетекшілерді көру')
    elif sup_state == 'pending':
        nxt = ('Жетекші өтінімі қаралуда', 'Өтініміңізді жетекші мен әкімші бекіткенін күтіңіз.', 'student_teachers', 'Өтінімді көру')
    elif top_state == 'todo':
        nxt = ('Тақырып таңдаңыз', 'Жетекшіңіздің тақырыптарынан біреуін таңдаңыз немесе өз тақырыбыңызды ұсыныңыз.', 'student_topics', 'Тақырыптарды көру')
    elif top_state == 'pending':
        nxt = ('Тақырып өтінімі қаралуда', 'Тақырыбыңызды жетекші мен әкімші бекіткенін күтіңіз.', 'student_topics', 'Өтінімді көру')
    else:
        nxt = ('Жұмыс барысын жүктеңіз', 'Әр кезең бойынша файлдарды жүктеп, жетекшіңізден кері байланыс алыңыз.', 'student_progress', 'Файл жүктеу')

    ctx.update({
        'files': files, 'sup_state': sup_state, 'top_state': top_state, 'pro_state': pro_state, 'next': nxt,
        'steps': [('Жетекші', sup_state, False), ('Тақырып', top_state, sup_state == 'done'), ('Барысы', pro_state, top_state == 'done')],
        'sup_history': s.supervisor_requests.select_related('teacher'),
        'app_history': s.applications.select_related('topic'),
        'active': 'home',
    })
    return render(request, 'student/home.html', ctx)


@role_required('student')
def student_teachers(request):
    s, ctx = _student_ctx(request)
    teachers = Teacher.objects.annotate(
        cs_taken_n=Count('students', filter=Q(students__major='CS'), distinct=True),
        students_n=Count('students', distinct=True),
    ).prefetch_related('topics')
    directory = []
    for t in teachers:
        topics = [tp for tp in t.topics.all() if tp.proposed_by == 'teacher' and tp.status in ('approved', 'taken')]
        topics.sort(key=lambda tp: (tp.status == 'taken', tp.id))
        directory.append({
            'obj': t, 'topics': topics,
            'cs_taken': t.cs_taken_n, 'cs_remaining': max(0, t.cs_quota - t.cs_taken_n),
            'students': t.students_n, 'topics_total': len(topics),
            'topics_free': sum(1 for tp in topics if tp.status == 'approved'),
        })
    ctx.update({'directory': directory, 'active': 'teachers',
                'can_request': not s.teacher_id and not S.has_open_request(s)})
    return render(request, 'student/teachers.html', ctx)


@role_required('student')
def student_topics(request):
    s, ctx = _student_ctx(request)
    open_topics = []
    if s.teacher_id:
        open_topics = Topic.objects.filter(teacher_id=s.teacher_id, proposed_by='teacher', status='approved').annotate(
            open_apps=Count('applications', filter=~Q(applications__teacher_status='rejected') & ~Q(applications__admin_status='rejected'))
        ).order_by('id')
    ctx.update({
        'open_topics': open_topics, 'active': 'topics',
        'can_apply': bool(s.teacher_id) and not s.topic_id and not S.has_open_application(s),
        'app_history': s.applications.select_related('topic'),
    })
    return render(request, 'student/topics.html', ctx)


@role_required('student')
def student_progress(request):
    s, ctx = _student_ctx(request)
    ctx.update({'files': s.files.all(), 'active': 'progress', 'accept': ','.join('.' + e for e in sorted(UPLOAD_EXT))})
    return render(request, 'student/progress.html', ctx)


@require_POST
@role_required('student')
def student_request_supervisor(request):
    s = S.student_profile(request.user)
    teacher = get_object_or_404(Teacher, pk=request.POST.get('teacher_id'))
    if run(request, S.request_supervisor, s, teacher, request.POST.get('message', '')):
        messages.success(request, 'Өтінім жіберілді! Жетекші мен әкімші бекіткеннен кейін ол сіздің ғылыми жетекшіңіз болады.')
    return redirect('student_teachers')


@require_POST
@role_required('student')
def student_apply_topic(request):
    s = S.student_profile(request.user)
    topic = get_object_or_404(Topic, pk=request.POST.get('topic_id'))
    if run(request, S.apply_for_topic, s, topic):
        messages.success(request, 'Тақырыпқа өтінім жіберілді! Жетекші мен әкімші бекіткенін күтіңіз.')
    return redirect('student_topics')


@require_POST
@role_required('student')
def student_propose_topic(request):
    s = S.student_profile(request.user)
    if run(request, S.propose_own_topic, s, request.POST.get('title'), request.POST.get('description')):
        messages.success(request, 'Тақырыбыңыз жіберілді! Жетекші мен әкімші бекіткеннен кейін ол ресми бекітіледі.')
    return redirect('student_topics')


@require_POST
@role_required('student')
def student_upload(request):
    s = S.student_profile(request.user)
    title = request.POST.get('title', '').strip()
    up = request.FILES.get('file')
    if not s.topic_id:
        messages.error(request, 'Файл жүктеу үшін тақырыбыңыз ресми бекітілуі керек.')
    elif not title:
        messages.error(request, 'Кезең атауын енгізіңіз.')
    elif not up:
        messages.error(request, 'Файлды таңдаңыз.')
    elif up.size > UPLOAD_MAX:
        messages.error(request, 'Файл 20 MB-тан аспауы керек.')
    elif os.path.splitext(up.name)[1].lower().lstrip('.') not in UPLOAD_EXT:
        messages.error(request, 'Бұл файл түріне рұқсат жоқ. Рұқсат етілген: ' + ', '.join(sorted(UPLOAD_EXT)))
    else:
        ProgressFile.objects.create(student=s, topic_id=s.topic_id, title=title[:200],
                                    note=request.POST.get('note', '').strip(), file=up, original_name=up.name[:255])
        messages.success(request, 'Файл жүктелді! Жетекшіңіз оны өз кабинетінен көре алады.')
    return redirect('student_progress')


# =====================================================================  Teacher

def _teacher_counts(t):
    open_teacher = Q(teacher_status='pending') & ~Q(admin_status='rejected')
    return {
        'requests': t.supervisor_requests.filter(open_teacher).count(),
        'applications': Application.objects.filter(open_teacher, topic__teacher=t).count(),
        'students': t.students.count(),
        'cs_taken': t.cs_taken,
        'cs_quota': t.cs_quota,
        'unreviewed': ProgressFile.objects.filter(student__teacher=t, teacher_comment='').count(),
    }


@role_required('teacher')
def teacher_home(request):
    t = S.teacher_profile(request.user)
    counts = _teacher_counts(t)
    return render(request, 'teacher/home.html', {
        'teacher': t, 'counts': counts, 'active': 'home',
        'cs_full': counts['cs_taken'] >= counts['cs_quota'],
        'requests': t.supervisor_requests.select_related('student'),
        'applications': Application.objects.filter(topic__teacher=t).select_related('student', 'topic'),
    })


@role_required('teacher')
def teacher_topics(request):
    t = S.teacher_profile(request.user)
    topics = t.topics.filter(proposed_by='teacher').select_related('student')
    order = {'pending': 0, 'approved': 1, 'taken': 2, 'rejected': 3}
    topics = sorted(topics, key=lambda x: (order.get(x.status, 9), -x.id))
    by = {k: sum(1 for x in topics if x.status == k) for k in order}
    return render(request, 'teacher/topics.html', {
        'teacher': t, 'topics': topics, 'by': by, 'counts': _teacher_counts(t), 'active': 'topics',
    })


@role_required('teacher')
def teacher_students(request):
    t = S.teacher_profile(request.user)
    open_apps = Prefetch('applications', queryset=Application.objects.filter(S.OPEN).select_related('topic'),
                         to_attr='open_apps')
    students = (t.students.select_related('topic')
                .prefetch_related('files', open_apps)                 # N+1 жоқ: 3 сұраныс барлық студентке
                .annotate(files_n=Count('files', distinct=True), last_upload=Max('files__created_at'),
                          unreviewed=Count('files', filter=Q(files__teacher_comment=''), distinct=True)))
    rows = [{'s': s, 'pending': None if s.topic_id else (s.open_apps[0] if s.open_apps else None)} for s in students]
    return render(request, 'teacher/students.html', {
        'teacher': t, 'rows': rows, 'counts': _teacher_counts(t), 'active': 'students',
    })


@require_POST
@role_required('teacher')
def teacher_review_request(request, pk):
    run(request, S.review_supervisor_request, pk, 'teacher', request.POST.get('decision'), S.teacher_profile(request.user))
    return redirect('/teacher/#requests')


@require_POST
@role_required('teacher')
def teacher_review_application(request, pk):
    run(request, S.review_application, pk, 'teacher', request.POST.get('decision'), S.teacher_profile(request.user))
    return redirect('/teacher/#applications')


@require_POST
@role_required('teacher')
def teacher_comment(request, pk):
    t = S.teacher_profile(request.user)
    run(request, S.comment_progress, pk, t, request.POST.get('comment'))
    sid = request.POST.get('student_id', '')
    return redirect(f'/teacher/students/#s{sid}' if sid.isdigit() else 'teacher_students')


# =====================================================================  Admin panel

@role_required('admin')
def panel(request):
    teachers = Teacher.objects.annotate(
        cs_taken_n=Count('students', filter=Q(students__major='CS'), distinct=True),
        students_n=Count('students', distinct=True),
        topics_n=Count('topics', filter=Q(topics__proposed_by='teacher', topics__status__in=['approved', 'taken']), distinct=True),
        topics_free=Count('topics', filter=Q(topics__proposed_by='teacher', topics__status='approved'), distinct=True),
    )
    teachers = list(teachers)
    for t in teachers:
        t.rem = max(0, t.cs_quota - t.cs_taken_n)
    sup = list(SupervisorRequest.objects.select_related('student', 'teacher'))
    cs_taken = {t.id: t.cs_taken_n for t in teachers}
    for r in sup:
        r.cs_taken = cs_taken.get(r.teacher_id, 0)
        r.cs_full = r.student.major == 'CS' and r.cs_taken >= r.teacher.cs_quota
    key = lambda o: (not (o.admin_status == 'pending' and o.teacher_status != 'rejected'), -o.id)
    return render(request, 'panel/review.html', {
        'counts': S.admin_counts(), 'active': 'review',
        'sup': sorted(sup, key=key),
        'apps': sorted(Application.objects.select_related('student', 'topic__teacher'), key=key),
        'topics': Topic.objects.filter(proposed_by='teacher').select_related('teacher').order_by('-id'),
        'teachers': teachers,
    })


@require_POST
@role_required('admin')
def panel_review_request(request, pk):
    run(request, S.review_supervisor_request, pk, 'admin', request.POST.get('decision'))
    return redirect('/panel/#supervisors')


@require_POST
@role_required('admin')
def panel_review_application(request, pk):
    run(request, S.review_application, pk, 'admin', request.POST.get('decision'))
    return redirect('/panel/#applications')


@require_POST
@role_required('admin')
def panel_review_topic(request, pk):
    run(request, S.admin_review_topic, pk, request.POST.get('decision'), request.user)
    return redirect('/panel/#topics')


@require_POST
@role_required('admin')
def panel_quota(request, pk):
    t = get_object_or_404(Teacher, pk=pk)
    try:
        t.cs_quota = max(0, min(50, int(request.POST.get('cs_quota', t.cs_quota))))
        t.save(update_fields=['cs_quota'])
        messages.success(request, 'Квота жаңартылды.')
    except ValueError:
        messages.error(request, 'Квота сан болуы керек.')
    return redirect('/panel/#quotas')


# ---------- Кестелер: толық CRUD (create / read / update / delete) ----------

TABLES = {
    'teachers': (Teacher, TeacherForm, 'Оқытушылар', ['full_name', 'academic_title', 'department', 'cs_quota', 'user']),
    'students': (Student, StudentForm, 'Студенттер', ['full_name', 'group_name', 'major', 'teacher', 'topic']),
    'topics': (Topic, TopicForm, 'Тақырыптар', ['title', 'teacher', 'proposed_by', 'status', 'created_at']),
    'requests': (SupervisorRequest, None, 'Жетекші өтінімдері', ['student', 'teacher', 'teacher_status', 'admin_status', 'created_at']),
    'applications': (Application, None, 'Тақырып өтінімдері', ['student', 'topic', 'teacher_status', 'admin_status', 'created_at']),
    'files': (ProgressFile, None, 'Жұмыс файлдары', ['student', 'title', 'original_name', 'teacher_comment', 'created_at']),
}
STATUS_FIELDS = {'status', 'teacher_status', 'admin_status'}


def _table(name):
    if name not in TABLES:
        raise Http404
    return TABLES[name]


@role_required('admin')
def panel_table(request, name):
    model, form_cls, title, cols = _table(name)
    q = request.GET.get('q', '').strip()
    fk = [f.name for f in model._meta.fields if f.is_relation and f.name in cols]
    qs = model.objects.select_related(*fk).order_by('-id')          # FK бағандары → JOIN, N+1 жоқ
    if q:
        text_fields = [f.name for f in model._meta.fields if f.get_internal_type() in ('CharField', 'TextField')]
        cond = Q()
        for f in text_fields:
            cond |= Q(**{f'{f}__icontains': q})
        qs = qs.filter(cond)
    page = Paginator(qs, 10).get_page(request.GET.get('page'))
    labels = {f.name: f.verbose_name for f in model._meta.fields}
    rows = [{'obj': o, 'cells': [(c, getattr(o, c)) for c in cols]} for o in page]
    return render(request, 'panel/table.html', {
        'counts': S.admin_counts(), 'active': name, 'name': name, 'title': title, 'page': page, 'rows': rows, 'q': q,
        'headers': [labels.get(c, c) for c in cols], 'status_fields': STATUS_FIELDS, 'editable': form_cls is not None,
    })


@role_required('admin')
def panel_edit(request, name, pk=None):
    model, form_cls, title, _ = _table(name)
    if form_cls is None:
        raise Http404
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_cls(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Жазба сақталды.' if obj else 'Жазба қосылды.')
        return redirect('panel_table', name=name)
    return render(request, 'panel/edit.html', {
        'counts': S.admin_counts(), 'active': name, 'name': name, 'title': title, 'form': form, 'obj': obj,
    })


@require_POST
@role_required('admin')
def panel_delete(request, name, pk):
    model, *_ = _table(name)
    get_object_or_404(model, pk=pk).delete()
    messages.success(request, 'Жазба өшірілді.')
    return redirect('panel_table', name=name)
