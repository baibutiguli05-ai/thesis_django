"""
Тақырып таңдау жүйесінің бизнес-логикасы (веб-беттер де, REST API де осыны қолданады).

  1) Студент жетекшіге өтінім жібереді → SupervisorRequest (оқытушы + әкімші бекітеді)
  2) Жетекші бекітілген соң тақырып таңдайды / өз тақырыбын ұсынады → Application (оқытушы + әкімші)
  3) Тақырып бекітілген соң жұмыс барысын жүктейді → ProgressFile
  Оқытушы ұсынған тақырыпты тек әкімші бекітеді (Topic.status).

Әр функция сәтсіз болса ServiceError шығарады (хабарламасы пайдаланушыға көрсетіледі).
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Application, ProgressFile, Student, SupervisorRequest, Teacher, Topic, overall_status


class ServiceError(Exception):
    pass


OPEN = Q(teacher_status='pending', admin_status='pending') | \
       Q(teacher_status='approved', admin_status='pending') | \
       Q(teacher_status='pending', admin_status='approved')


def _other(actor):
    return 'жетекшінің' if actor == 'admin' else 'әкімшінің'


# ------------------------------------------------------------------ студент

def has_open_request(student):
    return student.supervisor_requests.filter(OPEN).exists()


def has_open_application(student):
    return student.applications.filter(OPEN).exists()


def request_supervisor(student, teacher, message=''):
    if student.teacher_id:
        raise ServiceError('Сізде бекітілген жетекші бар.')
    if has_open_request(student):
        raise ServiceError('Сіздің өтініміңіз әлі қаралуда. Жауапты күтіңіз.')
    if student.major == 'CS' and teacher.cs_remaining <= 0:
        raise ServiceError('Бұл жетекшіде CS мамандығы үшін бос орын қалмады.')
    return SupervisorRequest.objects.create(student=student, teacher=teacher, message=(message or '').strip())


def apply_for_topic(student, topic):
    if not student.teacher_id:
        raise ServiceError('Алдымен жетекшіңіз бекітілуі керек.')
    if student.topic_id:
        raise ServiceError('Сізде бекітілген тақырып бар.')
    if topic.teacher_id != student.teacher_id:
        raise ServiceError('Тек өз жетекшіңіздің тақырыптарын таңдай аласыз.')
    if topic.status != 'approved' or topic.proposed_by != 'teacher':
        raise ServiceError('Бұл тақырыпты таңдау мүмкін емес.')
    if has_open_application(student):
        raise ServiceError('Сіздің тақырып өтініміңіз әлі қаралуда.')
    return Application.objects.create(student=student, topic=topic)


@transaction.atomic
def propose_own_topic(student, title, description=''):
    title = (title or '').strip()
    if not title:
        raise ServiceError('Тақырып атауын енгізіңіз.')
    if not student.teacher_id:
        raise ServiceError('Алдымен жетекшіңіз бекітілуі керек.')
    if student.topic_id:
        raise ServiceError('Сізде бекітілген тақырып бар.')
    if has_open_application(student):
        raise ServiceError('Сіздің тақырып өтініміңіз әлі қаралуда.')
    topic = Topic.objects.create(title=title, description=(description or '').strip(),
                                 teacher_id=student.teacher_id, proposed_by='student', status='pending')
    return Application.objects.create(student=student, topic=topic)


# ------------------------------------------------------------------ екі сатылы бекіту

def _check_decision(decision):
    if decision not in ('approved', 'rejected'):
        raise ServiceError('Қате шешім.')


@transaction.atomic
def review_supervisor_request(req_id, actor, decision, teacher=None):
    """actor: 'teacher' | 'admin'. Оқытушы тек өзіне келген өтінімді қарай алады."""
    _check_decision(decision)
    try:
        r = SupervisorRequest.objects.select_for_update().select_related('student', 'teacher').get(pk=req_id)
    except SupervisorRequest.DoesNotExist:
        raise ServiceError('Өтінім табылмады.')
    if actor == 'teacher' and (teacher is None or r.teacher_id != teacher.id):
        raise ServiceError('Бұл өтінім сізге жіберілмеген.')
    if r.status != 'pending':
        raise ServiceError('Бұл өтінім бұрын қаралған.')

    if decision == 'approved':
        if r.student.teacher_id:
            raise ServiceError('Студенттің жетекшісі бекітіліп қойған.')
        if r.student.major == 'CS' and r.teacher.cs_remaining <= 0:
            raise ServiceError('Жетекшінің CS квотасы толған — өтінімді бекіту мүмкін емес.')

    field = 'admin_status' if actor == 'admin' else 'teacher_status'
    setattr(r, field, decision)
    r.updated_at = timezone.now()
    r.save(update_fields=[field, 'updated_at'])

    if decision == 'rejected':
        return 'Өтінім қабылданбады.'
    if r.status == 'approved':
        Student.objects.filter(pk=r.student_id).update(teacher=r.teacher)
        return 'Өтінім толық бекітілді — студент жетекшіге тіркелді.'
    return f'Бекітілді. Енді {_other(actor)} шешімі күтілуде.'


@transaction.atomic
def review_application(app_id, actor, decision, teacher=None):
    _check_decision(decision)
    try:
        a = Application.objects.select_for_update().select_related('student', 'topic').get(pk=app_id)
    except Application.DoesNotExist:
        raise ServiceError('Өтінім табылмады.')
    if actor == 'teacher' and (teacher is None or a.topic.teacher_id != teacher.id):
        raise ServiceError('Бұл өтінім сізге жіберілмеген.')
    if a.status != 'pending':
        raise ServiceError('Бұл өтінім бұрын қаралған.')
    if decision == 'approved':
        if a.student.topic_id:
            raise ServiceError('Студенттің тақырыбы бекітіліп қойған.')
        if a.topic.status == 'taken':
            raise ServiceError('Бұл тақырыпты басқа студент алып қойған.')

    field = 'admin_status' if actor == 'admin' else 'teacher_status'
    setattr(a, field, decision)
    a.updated_at = timezone.now()
    a.save(update_fields=[field, 'updated_at'])

    if decision == 'rejected':
        if a.topic.proposed_by == 'student':
            Topic.objects.filter(pk=a.topic_id).update(status='rejected', reviewed_at=timezone.now())
        return 'Тақырып өтінімі қабылданбады.'

    if a.status == 'approved':
        # Ресми бекіту: тақырып студентке бекітіліп, «таңдалған» болады
        Student.objects.filter(pk=a.student_id).update(topic=a.topic)
        Topic.objects.filter(pk=a.topic_id).update(status='taken', reviewed_at=timezone.now())
        # Сол тақырыпқа басқа студенттердің ашық өтінімдері автоматты түрде қабылданбайды
        a.topic.applications.exclude(pk=a.pk).filter(OPEN).update(admin_status='rejected', updated_at=timezone.now())
        return 'Тақырып ресми бекітілді!'
    return f'Бекітілді. Енді {_other(actor)} шешімі күтілуде.'


# ------------------------------------------------------------------ оқытушы / әкімші

def create_teacher_topic(teacher, title, description=''):
    title = (title or '').strip()
    if not title:
        raise ServiceError('Тақырып атауын енгізіңіз.')
    return Topic.objects.create(teacher=teacher, title=title, description=(description or '').strip(),
                                proposed_by='teacher', status='pending')


def teacher_can_edit(topic, teacher):
    """Оқытушы өз тақырыбын студент алмаған кезде өзгерте / өшіре алады."""
    return topic.teacher_id == teacher.id and topic.proposed_by == 'teacher' and topic.status != 'taken'


def update_teacher_topic(topic, teacher, title, description=''):
    if not teacher_can_edit(topic, teacher):
        raise ServiceError('Бұл тақырыпты өзгерту мүмкін емес.')
    title = (title or '').strip()
    if not title:
        raise ServiceError('Тақырып атауын енгізіңіз.')
    topic.title, topic.description = title, (description or '').strip()
    # Мазмұны өзгерген тақырып қайта тексеруге жіберіледі
    topic.status, topic.reviewed_at, topic.reviewed_by = 'pending', None, None
    topic.save()
    topic.applications.filter(OPEN).update(admin_status='rejected', updated_at=timezone.now())
    return topic


def delete_teacher_topic(topic, teacher):
    if not teacher_can_edit(topic, teacher):
        raise ServiceError('Бұл тақырыпты өшіру мүмкін емес.')
    topic.delete()


def admin_review_topic(topic_id, decision, admin_user):
    _check_decision(decision)
    n = Topic.objects.filter(pk=topic_id, proposed_by='teacher', status='pending') \
        .update(status=decision, reviewed_by=admin_user, reviewed_at=timezone.now())
    if not n:
        raise ServiceError('Тақырып табылмады немесе бұрын қаралған.')
    return 'Тақырып бекітілді — енді студенттерге көрінеді.' if decision == 'approved' else 'Тақырып қабылданбады.'


def comment_progress(file_id, teacher, comment):
    try:
        f = ProgressFile.objects.get(pk=file_id, student__teacher=teacher)
    except ProgressFile.DoesNotExist:
        raise ServiceError('Файл табылмады.')
    f.teacher_comment = (comment or '').strip()
    f.commented_at = timezone.now() if f.teacher_comment else None
    f.save(update_fields=['teacher_comment', 'commented_at'])
    return 'Пікір сақталды.'


def file_visible_to(user, f):
    if user.is_staff:
        return True
    if hasattr(user, 'student') and f.student_id == user.student.id:
        return True
    if hasattr(user, 'teacher') and f.student.teacher_id == user.teacher.id:
        return True
    return False


# ------------------------------------------------------------------ рөлдер

def role_of(user):
    if not user.is_authenticated:
        return None
    if user.is_staff:
        return 'admin'
    if hasattr(user, 'teacher'):
        return 'teacher'
    return 'student'


def student_profile(user):
    s = getattr(user, 'student', None)
    if s is None:
        s = Student.objects.create(user=user, full_name=user.get_full_name() or user.username)
    return s


def teacher_profile(user):
    t = getattr(user, 'teacher', None)
    if t is None:
        t = Teacher.objects.create(user=user, full_name=user.get_full_name() or user.username)
    return t


def admin_counts():
    open_admin = Q(admin_status='pending') & ~Q(teacher_status='rejected')
    return {
        'supervisor': SupervisorRequest.objects.filter(open_admin).count(),
        'topics': Application.objects.filter(open_admin).count(),
        'teacher_topics': Topic.objects.filter(proposed_by='teacher', status='pending').count(),
        'students': Student.objects.count(),
        'assigned': Student.objects.filter(teacher__isnull=False).count(),
        'with_topic': Student.objects.filter(topic__isnull=False).count(),
    }
