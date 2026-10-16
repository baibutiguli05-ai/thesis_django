"""
Тесттер:  python manage.py test thesis
"""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from . import services as S
from django.db import IntegrityError, transaction

from .models import Application, ProgressFile, Student, SupervisorRequest, Tag, Teacher, Topic, overall_status

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', stdout=io.StringIO())

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def st(self, login):
        return Student.objects.get(user__username=login)

    def te(self, login):
        return Teacher.objects.get(user__username=login)

    def topic(self, title_start):
        return Topic.objects.get(title__startswith=title_start)


class WorkflowTests(Base):
    def test_full_supervisor_and_topic_flow(self):
        beibit, talgar = self.st('beibit'), self.te('talgar')
        self.assertEqual(talgar.cs_remaining, 1)
        r = S.request_supervisor(beibit, talgar, 'test')
        with self.assertRaises(S.ServiceError):
            S.request_supervisor(beibit, self.te('sholpan'))            # қайталанған өтінім
        with self.assertRaises(S.ServiceError):
            S.review_supervisor_request(r.id, 'teacher', 'approved', self.te('sholpan'))  # бөтен оқытушы
        S.review_supervisor_request(r.id, 'teacher', 'approved', talgar)
        self.assertIsNone(self.st('beibit').teacher_id)                  # әлі түпкілікті емес
        S.review_supervisor_request(r.id, 'admin', 'approved')
        beibit = self.st('beibit')
        self.assertEqual(beibit.teacher_id, talgar.id)
        self.assertEqual(Teacher.objects.get(pk=talgar.pk).cs_remaining, 0)

        arman_req = SupervisorRequest.objects.get(student__user__username='arman')
        with self.assertRaises(S.ServiceError):                          # квота толды
            S.review_supervisor_request(arman_req.id, 'admin', 'approved')

        free = self.topic('Жол белгілерін')
        with self.assertRaises(S.ServiceError):
            S.apply_for_topic(beibit, self.topic('Микросервистік'))      # басқа жетекшінің тақырыбы
        with self.assertRaises(S.ServiceError):
            S.apply_for_topic(beibit, self.topic('Видеодағы'))           # бекітілмеген тақырып
        a = S.apply_for_topic(beibit, free)
        with self.assertRaises(S.ServiceError):
            S.apply_for_topic(beibit, free)
        S.review_application(a.id, 'admin', 'approved')
        self.assertIsNone(self.st('beibit').topic_id)
        S.review_application(a.id, 'teacher', 'approved', talgar)
        self.assertEqual(self.st('beibit').topic_id, free.id)
        self.assertEqual(Topic.objects.get(pk=free.pk).status, 'taken')
        with self.assertRaises(S.ServiceError):
            S.review_application(a.id, 'admin', 'rejected')

    def test_student_topic_reject_then_propose(self):
        z = self.st('zhanerke')
        a = Application.objects.get(student=z)
        S.review_application(a.id, 'teacher', 'rejected', self.te('talgar'))
        self.assertEqual(Topic.objects.get(pk=a.topic_id).status, 'rejected')
        S.propose_own_topic(z, 'Жаңа тақырып', 'сипаттама')
        with self.assertRaises(S.ServiceError):
            S.propose_own_topic(self.st('nursultan'), 'X')

    def test_teacher_topic_crud_and_admin_review(self):
        y = self.te('yerlan')
        t = S.create_teacher_topic(y, 'Тест', '')
        self.assertEqual(t.status, 'pending')
        S.admin_review_topic(t.id, 'approved', None)
        t.refresh_from_db()
        self.assertEqual(t.status, 'approved')
        S.update_teacher_topic(t, y, 'Тест 2', 'жаңа')
        t.refresh_from_db()
        self.assertEqual((t.title, t.status), ('Тест 2', 'pending'))  # өзгергеннен кейін қайта тексеріледі
        with self.assertRaises(S.ServiceError):
            S.delete_teacher_topic(self.topic('Терең оқыту'), self.te('talgar'))   # студент алған тақырып
        S.delete_teacher_topic(t, y)
        self.assertFalse(Topic.objects.filter(pk=t.pk).exists())

    def test_files_permissions(self):
        f = ProgressFile.objects.filter(student__user__username='ansar').first()
        with self.assertRaises(S.ServiceError):
            S.comment_progress(f.id, self.te('sholpan'), 'x')
        S.comment_progress(f.id, self.te('talgar'), 'Жарайсың')
        self.assertTrue(S.file_visible_to(self.st('ansar').user, f))
        self.assertTrue(S.file_visible_to(self.te('talgar').user, f))
        self.assertFalse(S.file_visible_to(self.te('sholpan').user, f))
        self.assertFalse(S.file_visible_to(self.st('beibit').user, f))


class WebTests(Base):
    PAGES = {
        'beibit': ['student_home', 'student_teachers', 'student_topics', 'student_progress'],
        'ansar': ['student_home', 'student_teachers', 'student_topics', 'student_progress'],
        'talgar': ['teacher_home', 'teacher_topics', 'teacher_students'],
        'admin': ['panel'],
    }

    def login(self, u):
        self.assertTrue(self.client.login(username=u, password='beibit123'))

    def test_all_pages_render(self):
        for user, pages in self.PAGES.items():
            self.client.logout()
            self.login(user)
            for name in pages:
                r = self.client.get(reverse(name))
                self.assertEqual(r.status_code, 200, f'{user} {name}')
        for t in ['teachers', 'students', 'topics', 'requests', 'applications', 'files']:
            self.assertEqual(self.client.get(reverse('panel_table', args=[t])).status_code, 200, t)
        self.assertEqual(self.client.get(reverse('panel_create', args=['topics'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel_edit', args=['teachers', self.te('talgar').id])).status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_login_register_and_roles(self):
        r = self.client.post(reverse('login'), {'username': 'talgar', 'password': 'beibit123'})
        self.assertRedirects(r, reverse('home'), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('home')), reverse('teacher_home'))
        # оқытушы әкімші панеліне кіре алмайды
        self.assertRedirects(self.client.get(reverse('panel')), reverse('home'), fetch_redirect_response=False)
        self.client.logout()
        r = self.client.post(reverse('login'), {'username': 'talgar', 'password': 'wrong'})
        self.assertContains(r, 'қате')
        r = self.client.post(reverse('register'), {'full_name': 'Aibar Bolat', 'username': 'aibar', 'password': 'abc', 'role': 'student'})
        self.assertContains(r, 'кемінде 6')
        r = self.client.post(reverse('register'), {'full_name': 'Aibar Bolat', 'username': 'aibar', 'password': 'Pass1234', 'role': 'student'})
        self.assertRedirects(r, reverse('login'))
        self.assertTrue(Student.objects.filter(user__username='aibar').exists())

    def test_web_flow_with_upload(self):
        self.login('beibit')
        self.client.post(reverse('student_request_supervisor'), {'teacher_id': self.te('sholpan').id, 'message': 'hi'})
        req = SupervisorRequest.objects.get(student__user__username='beibit')
        self.client.logout(); self.login('sholpan')
        self.client.post(reverse('teacher_review_request', args=[req.id]), {'decision': 'approved'})
        self.client.logout(); self.login('admin')
        self.client.post(reverse('panel_review_request', args=[req.id]), {'decision': 'approved'})
        self.client.logout(); self.login('beibit')
        topic = self.topic('Микросервистік')
        self.client.post(reverse('student_apply_topic'), {'topic_id': topic.id})
        app = Application.objects.get(student__user__username='beibit')
        self.client.logout(); self.login('admin')
        self.client.post(reverse('panel_review_application', args=[app.id]), {'decision': 'approved'})
        self.client.logout(); self.login('sholpan')
        r = self.client.post(reverse('teacher_review_application', args=[app.id]), {'decision': 'approved'}, follow=True)
        self.assertContains(r, 'ресми бекітілді')
        self.client.logout(); self.login('beibit')
        r = self.client.post(reverse('student_upload'), {'title': '1-тарау', 'note': 'x',
                             'file': SimpleUploadedFile('ch1.txt', b'hello')}, follow=True)
        self.assertContains(r, 'Файл жүктелді')
        r = self.client.post(reverse('student_upload'), {'title': 'bad', 'file': SimpleUploadedFile('x.php', b'<?php')}, follow=True)
        self.assertContains(r, 'рұқсат жоқ')
        f = ProgressFile.objects.get(original_name='ch1.txt')
        self.assertEqual(b''.join(self.client.get(reverse('download', args=[f.id])).streaming_content), b'hello')
        self.client.logout(); self.login('talgar')
        self.assertEqual(self.client.get(reverse('download', args=[f.id])).status_code, 404)

    def test_admin_crud(self):
        self.login('admin')
        r = self.client.post(reverse('panel_create', args=['teachers']),
                             {'full_name': 'Gulnara Bekova', 'cs_quota': 2, 'academic_title': '', 'department': '',
                              'research_area': '', 'email': '', 'user': ''})
        self.assertRedirects(r, reverse('panel_table', args=['teachers']))
        t = Teacher.objects.get(full_name='Gulnara Bekova')
        self.client.post(reverse('panel_edit', args=['teachers', t.id]),
                         {'full_name': 'Gulnara Bekova', 'cs_quota': 7, 'academic_title': 'PhD', 'department': '',
                          'research_area': '', 'email': '', 'user': ''})
        t.refresh_from_db()
        self.assertEqual(t.cs_quota, 7)
        self.client.post(reverse('panel_delete', args=['teachers', t.id]))
        self.assertFalse(Teacher.objects.filter(pk=t.id).exists())

    def test_csrf_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.login(username='beibit', password='beibit123')
        r = c.post(reverse('student_request_supervisor'), {'teacher_id': self.te('sholpan').id})
        self.assertEqual(r.status_code, 403)


class ApiTests(Base):
    def api(self, user):
        c = APIClient()
        c.login(username=user, password='beibit123')
        return c

    def test_requires_auth(self):
        self.assertEqual(APIClient().get('/api/teachers/').status_code, 403)

    def test_basic_auth_and_me(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Basic YmVpYml0OmJlaWJpdDEyMw==')  # beibit:beibit123
        r = c.get('/api/me/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['role'], 'student')

    def test_teachers_readonly_for_students(self):
        c = self.api('beibit')
        r = c.get('/api/teachers/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 5)
        self.assertIn('cs_remaining', r.data['results'][0])
        self.assertEqual(c.post('/api/teachers/', {'full_name': 'X'}).status_code, 403)

    def test_full_api_flow(self):
        s, t, a = self.api('beibit'), self.api('sholpan'), self.api('admin')
        sholpan = self.te('sholpan')
        r = s.post('/api/supervisor-requests/', {'teacher': sholpan.id, 'message': 'API'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        rid = r.data['id']
        self.assertEqual(s.post('/api/supervisor-requests/', {'teacher': sholpan.id}, format='json').status_code, 400)
        self.assertEqual(s.post(f'/api/supervisor-requests/{rid}/review/', {'decision': 'approved'}, format='json').status_code, 403)
        self.assertEqual(t.post(f'/api/supervisor-requests/{rid}/review/', {'decision': 'approved'}, format='json').status_code, 200)
        r = a.post(f'/api/supervisor-requests/{rid}/review/', {'decision': 'approved'}, format='json')
        self.assertEqual(r.data['data']['status'], 'approved')

        r = s.post('/api/applications/propose/', {'title': 'API арқылы ұсынылған тақырып', 'description': 'd'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        aid = r.data['id']
        t.post(f'/api/applications/{aid}/review/', {'decision': 'approved'}, format='json')
        r = a.post(f'/api/applications/{aid}/review/', {'decision': 'approved'}, format='json')
        self.assertEqual(r.data['detail'], 'Тақырып ресми бекітілді!')

        r = s.post('/api/progress-files/', {'title': 'API файл', 'file': SimpleUploadedFile('a.pdf', b'%PDF')}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        fid = r.data['id']
        r = t.post(f'/api/progress-files/{fid}/comment/', {'comment': 'OK'}, format='json')
        self.assertEqual(r.data['data']['teacher_comment'], 'OK')
        self.assertEqual(self.api('talgar').get('/api/progress-files/').data['count'], 3)  # тек өз студенттері

    def test_topic_crud_api(self):
        y = self.api('yerlan')
        r = y.post('/api/topics/', {'title': 'API тақырып', 'description': 'd', 'status': 'approved'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['status'], 'pending')        # оқытушы статусты өзі қоя алмайды
        tid = r.data['id']
        r = y.patch(f'/api/topics/{tid}/', {'title': 'Өзгертілген'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.api('talgar').delete(f'/api/topics/{tid}/').status_code, 404)  # бөтен тақырып
        self.assertEqual(self.api('beibit').post(f'/api/topics/{tid}/review/', {'decision': 'approved'}, format='json').status_code, 403)
        r = self.api('admin').post(f'/api/topics/{tid}/review/', {'decision': 'approved'}, format='json')
        self.assertEqual(r.data['topic']['status'], 'approved')
        self.assertEqual(y.delete(f'/api/topics/{tid}/').status_code, 204)

    def test_scoping(self):
        self.assertEqual(self.api('beibit').get('/api/students/').data['count'], 1)
        self.assertEqual(self.api('talgar').get('/api/students/').data['count'], 3)
        self.assertEqual(self.api('admin').get('/api/students/').data['count'], 12)
        self.assertEqual(self.api('beibit').get('/api/supervisor-requests/').data['count'], 0)
        self.assertEqual(self.api('admin').get('/api/supervisor-requests/').data['count'], 11)


# =====================================================================  Модель тесттері

class ModelTests(Base):
    def test_overall_status(self):
        self.assertEqual(overall_status('approved', 'approved'), 'approved')
        self.assertEqual(overall_status('approved', 'pending'), 'pending')
        self.assertEqual(overall_status('pending', 'rejected'), 'rejected')

    def test_cs_quota_properties(self):
        t = self.te('talgar')                 # квота 4, CS студенттері: ansar, alikhan, zhanerke
        self.assertEqual((t.cs_quota, t.cs_taken, t.cs_remaining), (4, 3, 1))
        self.assertEqual(self.te('aigul').cs_remaining, 0)

    def test_str_and_absolute_url(self):
        topic = self.topic('Терең оқыту')
        self.assertEqual(str(topic), topic.title)
        self.assertEqual(topic.get_absolute_url(), f'/topics/{topic.pk}/')
        self.assertEqual(str(self.te('talgar')), 'Talgar Asel')

    def test_tags_many_to_many(self):
        topic = self.topic('Терең оқыту')
        names = set(topic.tags.values_list('name', flat=True))
        self.assertEqual(names, {'Машиналық оқыту', 'Компьютерлік көру', 'Медицина'})
        ml = Tag.objects.get(name='Машиналық оқыту')
        self.assertIn(topic, ml.topics.all())                      # кері байланыс
        self.assertGreaterEqual(ml.topics.count(), 5)

    def test_unique_title_per_teacher(self):
        t = self.te('talgar')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Topic.objects.create(teacher=t, title=self.topic('Терең оқыту').title)
        Topic.objects.create(teacher=self.te('sholpan'), title=self.topic('Терең оқыту').title)  # басқа оқытушыда — рұқсат

    def test_status_property_on_two_step(self):
        r = SupervisorRequest.objects.get(student__user__username='arman')
        self.assertEqual((r.teacher_status, r.admin_status, r.status), ('approved', 'pending', 'pending'))


# =====================================================================  CBV CRUD тесттері

class TopicCrudTests(Base):
    def login(self, u):
        self.assertTrue(self.client.login(username=u, password='beibit123'))

    def test_list_search_filter_sort_paginate(self):
        self.login('beibit')
        r = self.client.get(reverse('topic_list'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['paginator'].count, 12)           # студентке тек бекітілген/таңдалған
        self.assertEqual(len(r.context['topics']), 9)                # беттеу: 9
        self.assertEqual(r.context['stats']['taken'], 4)
        r = self.client.get(reverse('topic_list'), {'q': 'YOLO'})
        self.assertEqual([t.title for t in r.context['topics']], ['Жол белгілерін тану үшін YOLO моделін бейімдеу'])
        tag = Tag.objects.get(name='NLP')
        r = self.client.get(reverse('topic_list'), {'tag': tag.id})
        self.assertTrue(all(tag in t.tags.all() for t in r.context['topics']))
        r = self.client.get(reverse('topic_list'), {'teacher': self.te('aigul').id, 'sort': 'title'})
        titles = [t.title for t in r.context['topics']]
        self.assertEqual(titles, sorted(titles))
        self.assertEqual(len(titles), 2)
        r = self.client.get(reverse('topic_list'), {'page': 2})
        self.assertEqual(len(r.context['topics']), 3)

    def test_student_cannot_see_pending_or_modify(self):
        self.login('beibit')
        pending = self.topic('Видеодағы')
        self.assertEqual(self.client.get(reverse('topic_detail', args=[pending.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('topic_create')).status_code, 403)
        free = self.topic('Жол белгілерін')
        self.assertEqual(self.client.get(reverse('topic_update', args=[free.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse('topic_delete', args=[free.id])).status_code, 403)

    def test_detail_page(self):
        self.login('beibit')
        t = self.topic('Терең оқыту')
        r = self.client.get(reverse('topic_detail', args=[t.id]))
        self.assertContains(r, t.title)
        self.assertContains(r, '#Медицина')
        self.assertContains(r, 'Talgar Asel')
        self.assertTrue(len(r.context['similar']) > 0)

    def test_teacher_create_update_delete(self):
        self.login('yerlan')
        tags = Tag.objects.filter(name__in=['DevOps', 'Python'])
        r = self.client.post(reverse('topic_create'), {
            'title': 'Kubernetes кластерін мониторингтеу', 'description': 'Prometheus және Grafana арқылы метрикаларды жинау.',
            'tags': [t.id for t in tags]})
        topic = Topic.objects.get(title='Kubernetes кластерін мониторингтеу')
        self.assertRedirects(r, topic.get_absolute_url())
        self.assertEqual((topic.teacher, topic.status, topic.tags.count()), (self.te('yerlan'), 'pending', 2))

        S.admin_review_topic(topic.id, 'approved', None)
        self.client.post(reverse('topic_update', args=[topic.id]), {
            'title': 'Kubernetes кластерін бақылау жүйесі', 'description': 'Prometheus және Grafana арқылы метрикаларды жинау.',
            'tags': [tags[0].id]})
        topic.refresh_from_db()
        self.assertEqual((topic.title, topic.status, topic.tags.count()), ('Kubernetes кластерін бақылау жүйесі', 'pending', 1))

        r = self.client.get(reverse('topic_delete', args=[topic.id]))
        self.assertContains(r, 'Иә, өшіру')
        r = self.client.post(reverse('topic_delete', args=[topic.id]))
        self.assertRedirects(r, reverse('topic_list'))
        self.assertFalse(Topic.objects.filter(pk=topic.id).exists())

    def test_teacher_cannot_edit_foreign_or_taken(self):
        self.login('yerlan')
        foreign = self.topic('Жол белгілерін')
        self.assertEqual(self.client.get(reverse('topic_update', args=[foreign.id])).status_code, 403)
        self.client.logout(); self.login('talgar')
        taken = self.topic('Терең оқыту')
        self.assertEqual(self.client.get(reverse('topic_update', args=[taken.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse('topic_delete', args=[taken.id])).status_code, 403)

    def test_form_validation(self):
        self.login('talgar')
        url = reverse('topic_create')
        r = self.client.post(url, {'title': 'Қысқа', 'description': ''})
        self.assertFormError(r.context['form'], 'title', 'Тақырып атауы кемінде 10 таңбадан тұруы керек.')
        r = self.client.post(url, {'title': '1234567890123', 'description': ''})
        self.assertFormError(r.context['form'], 'title', 'Тақырып атауы тек сандардан тұрмауы керек.')
        r = self.client.post(url, {'title': 'Дұрыс атаулы тақырып', 'description': 'тым қысқа'})
        self.assertFormError(r.context['form'], 'description', 'Сипаттама кемінде 20 таңбадан тұруы керек (немесе бос қалдырыңыз).')
        r = self.client.post(url, {'title': self.topic('Терең оқыту').title.upper(), 'description': ''})
        self.assertFormError(r.context['form'], 'title', 'Бұл оқытушыда осындай атаулы тақырып бар.')
        r = self.client.post(url, {'title': 'Дұрыс атаулы тақырып', 'tags': list(Tag.objects.values_list('id', flat=True)[:6])})
        self.assertFormError(r.context['form'], 'tags', 'Ең көбі 5 тег таңдауға болады.')
        self.assertEqual(Topic.objects.filter(title='Дұрыс атаулы тақырып').count(), 0)

    def test_admin_can_set_teacher_and_status(self):
        self.login('admin')
        r = self.client.post(reverse('topic_create'), {
            'title': 'Әкімші қосқан тақырып атауы', 'description': '', 'teacher': self.te('nurlan').id, 'status': 'approved'})
        t = Topic.objects.get(title='Әкімші қосқан тақырып атауы')
        self.assertEqual((t.teacher.user.username, t.status), ('nurlan', 'approved'))

    def test_teacher_detail(self):
        self.login('beibit')
        r = self.client.get(reverse('teacher_detail', args=[self.te('talgar').id]))
        self.assertContains(r, 'Talgar Asel')
        self.assertEqual(r.context['cs_remaining'], 1)
        self.assertEqual(len(r.context['teacher_obj'].public_topics), 3)


# =====================================================================  N+1 тесттері (сұраныс саны тұрақты)

class QueryCountTests(Base):
    """Жазбалар саны өссе де, бет үшін SQL-сұраныстар саны өзгермеуі керек."""

    def _count(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(ctx.captured_queries)

    def _more_topics(self, n=12):
        t, tags = self.te('yerlan'), list(Tag.objects.all()[:3])
        for i in range(n):
            topic = Topic.objects.create(teacher=t, title=f'Қосымша тақырып нөмірі {i:02d}', status='approved')
            topic.tags.set(tags)

    def test_topic_list_constant_queries(self):
        self.client.login(username='admin', password='beibit123')
        before = self._count(reverse('topic_list') + '?sort=title')
        self._more_topics()
        self.assertEqual(self._count(reverse('topic_list') + '?sort=title'), before)

    def test_teacher_detail_constant_queries(self):
        self.client.login(username='beibit', password='beibit123')
        url = reverse('teacher_detail', args=[self.te('yerlan').id])
        before = self._count(url)
        self._more_topics()
        self.assertEqual(self._count(url), before)

    def test_teacher_students_constant_queries(self):
        self.client.login(username='talgar', password='beibit123')
        before = self._count(reverse('teacher_students'))
        talgar = self.te('talgar')
        for login in ('dana', 'arman'):
            Student.objects.filter(user__username=login).update(teacher=talgar)
        self.assertEqual(self._count(reverse('teacher_students')), before)

    def test_admin_tables_constant_queries(self):
        self.client.login(username='admin', password='beibit123')
        before = {t: self._count(reverse('panel_table', args=[t])) for t in ('students', 'topics', 'applications')}
        self._more_topics(5)
        for s in Student.objects.filter(topic__isnull=True)[:3]:
            Application.objects.create(student=s, topic=Topic.objects.filter(title__startswith='Қосымша').first())
        after = {t: self._count(reverse('panel_table', args=[t])) for t in before}
        self.assertEqual(after, before)

    def test_api_teachers_constant_queries(self):
        c = APIClient()
        c.login(username='admin', password='beibit123')
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as a:
            c.get('/api/teachers/')
        Teacher.objects.create(full_name='Жаңа оқытушы')
        with CaptureQueriesContext(connection) as b:
            c.get('/api/teachers/')
        self.assertEqual(len(a.captured_queries), len(b.captured_queries))
