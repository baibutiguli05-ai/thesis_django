"""
Демо-деректер:  python manage.py seed_demo
Барлық аккаунттардың құпия сөзі: beibit123   (әкімші: admin)
Қайта іске қосу демо-деректерді толық қалпына келтіреді.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from thesis.models import Application, ProgressFile, Student, SupervisorRequest, Tag, Teacher, Topic

PASSWORD = 'beibit123'

TEACHERS = [
    # login, аты-жөні, атағы, кафедра, бағыты, email, CS квота
    ('talgar',  'Talgar Asel',       'PhD, қауымдастырылған профессор', 'Компьютерлік ғылымдар кафедрасы',   'Машиналық оқыту, компьютерлік көру',        'a.talgar@univer.kz',     4),
    ('sholpan', 'Sholpan Amual',     'Аға оқытушы, магистр',            'Ақпараттық жүйелер кафедрасы',      'Веб-әзірлеу, дерекқорлар',                  's.amual@univer.kz',      3),
    ('nurlan',  'Nurlan Sarsenov',   'Профессор, т.ғ.д.',               'Компьютерлік ғылымдар кафедрасы',   'Деректер ғылымы, табиғи тілді өңдеу (NLP)', 'n.sarsenov@univer.kz',   5),
    ('aigul',   'Aigul Akhmetova',   'PhD, доцент',                     'Ақпараттық қауіпсіздік кафедрасы',  'Киберқауіпсіздік, желілік қорғау',          'a.akhmetova@univer.kz',  1),
    ('yerlan',  'Yerlan Zhumabayev', 'Аға оқытушы, PhD',                'Бағдарламалық инженерия кафедрасы', 'Мобильді әзірлеу, DevOps',                  'e.zhumabayev@univer.kz', 3),
]

# (оқытушы login, атауы, сипаттамасы, статус)
TOPICS = [
    ('talgar',  'Терең оқыту негізінде медициналық кескіндерді сегментациялау', 'U-Net архитектурасы арқылы МРТ суреттеріндегі ісіктерді автоматты түрде анықтау.', 'approved'),
    ('talgar',  'Нақты уақыттағы бет-әлпетті тану жүйесі', 'OpenCV және FaceNet негізінде аудиториядағы қатысуды тіркеу жүйесі.', 'approved'),
    ('talgar',  'Жол белгілерін тану үшін YOLO моделін бейімдеу', 'Қазақстан жолдарындағы белгілердің деректер жиынын жинап, YOLOv8 моделін оқыту.', 'approved'),
    ('talgar',  'Видеодағы адам қозғалысын талдау', 'Pose estimation әдістері арқылы спорттық жаттығуларды бағалау.', 'pending'),
    ('sholpan', 'Дипломдық тақырып таңдауға арналған веб-жүйе', 'Django және PostgreSQL негізінде университет порталы.', 'approved'),
    ('sholpan', 'Микросервистік архитектурадағы электронды кітапхана', 'Docker және REST API негізінде кітапхана қызметтерін бөлу.', 'approved'),
    ('sholpan', 'PostgreSQL және MySQL өнімділігін салыстыру', 'Әртүрлі жүктемелер кезінде сұраныстардың орындалу уақытын зерттеу.', 'approved'),
    ('nurlan',  'Қазақ тіліндегі мәтіндердің тональдығын анықтау', 'Әлеуметтік желі пікірлерін BERT моделі арқылы жіктеу.', 'approved'),
    ('nurlan',  'Студенттердің үлгерімін болжау', 'Машиналық оқыту модельдерін салыстыру: Random Forest, XGBoost, нейрондық желі.', 'approved'),
    ('nurlan',  'Абитуриенттерге кеңес беретін чат-бот', 'RAG тәсілі арқылы университет ережелері бойынша сұрақтарға жауап беру.', 'approved'),
    ('nurlan',  'Ғылыми мақалаларды автоматты рефераттау', 'Ұзын мәтіндерді қысқаша мазмұндау әдістері.', 'rejected'),
    ('aigul',   'Веб-қосымшалардағы SQL-инъекцияны анықтау жүйесі', 'HTTP сұраныстарын талдап, шабуылдарды машиналық оқыту арқылы анықтау.', 'approved'),
    ('aigul',   'Фишингтік сайттарды анықтау', 'URL және бет мазмұны белгілері бойынша жіктеуіш құру.', 'approved'),
    ('yerlan',  'Flutter негізіндегі студенттік кесте қосымшасы', 'Сабақ кестесі, хабарламалар және офлайн режимі бар мобильді қосымша.', 'approved'),
    ('yerlan',  'CI/CD құбырын автоматтандыру', 'GitHub Actions және Docker арқылы университет жобаларын жариялау.', 'pending'),
]

# Тақырып нөмірі (1-ден) → тегтер (ManyToMany)
TOPIC_TAGS = {
    1: ['Машиналық оқыту', 'Компьютерлік көру', 'Медицина'],
    2: ['Компьютерлік көру', 'Python'],
    3: ['Компьютерлік көру', 'Машиналық оқыту'],
    4: ['Компьютерлік көру', 'Спорт'],
    5: ['Веб-әзірлеу', 'Дерекқор', 'Python'],
    6: ['Веб-әзірлеу', 'DevOps'],
    7: ['Дерекқор'],
    8: ['NLP', 'Машиналық оқыту'],
    9: ['Машиналық оқыту', 'Білім беру'],
    10: ['NLP', 'Білім беру'],
    11: ['NLP'],
    12: ['Киберқауіпсіздік', 'Веб-әзірлеу', 'Машиналық оқыту'],
    13: ['Киберқауіпсіздік'],
    14: ['Мобильді әзірлеу', 'Білім беру'],
    15: ['DevOps'],
}

STUDENTS = [
    # login, аты-жөні, топ, мамандық
    ('beibit',    'Beibitgul Serik',      'CS-2201', 'CS'),
    ('beibit1',   'Beibitgul',            'CS-2202', 'CS'),
    ('ansar',     'Serik Ansar',          'CS-2201', 'CS'),
    ('alikhan',   'Alikhan Bekuly',       'CS-2201', 'CS'),
    ('dana',      'Dana Serikova',        'CS-2202', 'CS'),
    ('arman',     'Arman Nurlanov',       'CS-2203', 'CS'),
    ('aruzhan',   'Aruzhan Toktarova',    'SE-2201', 'SE'),
    ('nursultan', 'Nursultan Abdirov',    'CS-2203', 'CS'),
    ('zhanerke',  'Zhanerke Muratkyzy',   'CS-2202', 'CS'),
    ('yerasyl',   'Yerasyl Kairatuly',    'IS-2201', 'IS'),
    ('madiyar',   'Madiyar Yerzhanov',    'CS-2201', 'CS'),
    ('tomiris',   'Tomiris Baurzhankyzy', 'CS-2203', 'CS'),
]


class Command(BaseCommand):
    help = 'Демо-аккаунттар мен деректерді жасайды (құпия сөз: beibit123)'

    @transaction.atomic
    def handle(self, *args, **opts):
        now = timezone.now()
        logins = ['admin'] + [t[0] for t in TEACHERS] + [s[0] for s in STUDENTS]

        # Тазалау
        for m in (ProgressFile, Application, SupervisorRequest, Student, Topic, Teacher, Tag):
            for obj in m.objects.all() if m is ProgressFile else []:
                obj.file.delete(save=False)
            m.objects.all().delete()
        User.objects.filter(username__in=logins).delete()

        def make_user(login, name, staff=False):
            u = User(username=login, first_name=name, is_staff=staff, is_superuser=staff)
            u.set_password(PASSWORD)
            u.save()
            return u

        make_user('admin', 'Administrator', staff=True)

        T = {}
        for login, name, title, dept, area, email, quota in TEACHERS:
            T[login] = Teacher.objects.create(user=make_user(login, name), full_name=name, academic_title=title,
                                              department=dept, research_area=area, email=email, cs_quota=quota)

        P = []
        for tl, title, desc, status in TOPICS:
            P.append(Topic.objects.create(teacher=T[tl], title=title, description=desc, proposed_by='teacher', status=status,
                                          reviewed_at=now if status != 'pending' else None))
        P = {i + 1: p for i, p in enumerate(P)}   # 1-ден басталатын нөмірлер

        tag_names = sorted({n for names in TOPIC_TAGS.values() for n in names})
        tags = {t.name: t for t in Tag.objects.bulk_create([Tag(name=n) for n in tag_names])}
        for no, names in TOPIC_TAGS.items():
            P[no].tags.set([tags[n] for n in names])

        S = {}
        for login, name, group, major in STUDENTS:
            S[login] = Student.objects.create(user=make_user(login, name), full_name=name, group_name=group, major=major)

        def assign(login, teacher, topic_no=None):
            s = S[login]
            s.teacher = T[teacher]
            if topic_no:
                s.topic = P[topic_no]
                P[topic_no].status = 'taken'
                P[topic_no].save()
            s.save()

        assign('ansar', 'talgar', 1)
        assign('alikhan', 'talgar', 2)
        assign('zhanerke', 'talgar')
        assign('nursultan', 'nurlan')
        assign('yerasyl', 'sholpan', 5)
        assign('tomiris', 'aigul', 12)

        def req(student, teacher, msg, ts, as_, days):
            r = SupervisorRequest.objects.create(student=S[student], teacher=T[teacher], message=msg, teacher_status=ts, admin_status=as_)
            SupervisorRequest.objects.filter(pk=r.pk).update(created_at=now - timedelta(days=days))

        req('ansar', 'talgar', 'Компьютерлік көру саласына қызығамын.', 'approved', 'approved', 30)
        req('alikhan', 'talgar', 'Python және OpenCV бойынша тәжірибем бар.', 'approved', 'approved', 29)
        req('nursultan', 'nurlan', 'NLP бағытында жұмыс істегім келеді.', 'approved', 'approved', 25)
        req('zhanerke', 'talgar', 'Дрон деректерін талдау тақырыбын ұсынғым келеді.', 'approved', 'approved', 22)
        req('yerasyl', 'sholpan', 'Веб-әзірлеу менің негізгі бағытым.', 'approved', 'approved', 28)
        req('tomiris', 'aigul', 'Ақпараттық қауіпсіздікке қызығамын.', 'approved', 'approved', 27)
        req('beibit1', 'sholpan', 'Дерекқорлар бойынша курстық жұмысым бар еді.', 'pending', 'pending', 2)
        req('dana', 'talgar', 'Машиналық оқыту бойынша Kaggle жарыстарына қатыстым.', 'pending', 'pending', 1)
        req('arman', 'talgar', 'Компьютерлік көру бойынша зерттеу жүргізгім келеді.', 'approved', 'pending', 3)
        req('aruzhan', 'nurlan', 'Мәтіндерді өңдеу тақырыбына қызығамын.', 'pending', 'pending', 4)
        req('madiyar', 'aigul', 'Желілік қауіпсіздік бойынша жұмыс жасағым келеді.', 'rejected', 'pending', 6)

        def app(student, topic, ts, as_, days):
            a = Application.objects.create(student=S[student], topic=topic, teacher_status=ts, admin_status=as_)
            Application.objects.filter(pk=a.pk).update(created_at=now - timedelta(days=days))

        app('ansar', P[1], 'approved', 'approved', 20)
        app('alikhan', P[2], 'approved', 'approved', 19)
        app('yerasyl', P[5], 'approved', 'approved', 21)
        app('tomiris', P[12], 'approved', 'approved', 18)
        app('nursultan', P[8], 'pending', 'pending', 2)
        own = Topic.objects.create(teacher=T['talgar'], proposed_by='student', status='pending',
                                   title='Дрон суреттерінен егін алқаптарын талдау',
                                   description='Студент ұсынған тақырып: NDVI индексі және CNN арқылы өсімдік күйін бағалау.')
        own.tags.set([tags['Компьютерлік көру'], tags['Машиналық оқыту']])
        app('zhanerke', own, 'pending', 'pending', 1)

        def upload(student, title, note, fname, text, days, comment=''):
            f = ProgressFile(student=S[student], topic=S[student].topic, title=title, note=note, original_name=fname,
                             teacher_comment=comment, commented_at=(now - timedelta(days=days - 2)) if comment else None)
            f.file.save(fname, ContentFile(text.encode('utf-8')), save=True)
            ProgressFile.objects.filter(pk=f.pk).update(created_at=now - timedelta(days=days))

        upload('ansar', 'Кіріспе және әдебиетке шолу', 'Бірінші тарау: зерттеудің өзектілігі және U-Net туралы шолу.', 'kirispe.txt',
               '1-тарау. Кіріспе және әдебиетке шолу\n\nU-Net (Ronneberger et al., 2015) — биомедициналық сегментацияның негізгі әдісі.\n', 10,
               'Жақсы бастама. Соңғы 3 жылдағы мақалаларды көбірек қосыңыз.')
        upload('ansar', 'Деректер жиынын дайындау', 'BraTS деректер жиынын жүктеп, алдын ала өңдеу жасадым.', 'dataset_report.txt',
               'BraTS 2021: 1251 МРТ зерттеуі. Нормалау, 128x128x128, аугментация.\n', 2)
        upload('alikhan', 'Жүйе архитектурасы', 'Жүйенің UML диаграммалары және модульдер сипаттамасы.', 'architecture.txt',
               'Камера → MTCNN → FaceNet → дерекқор → қатысуды тіркеу.\n', 4)
        upload('yerasyl', 'Дерекқор жобасы', 'ER-диаграмма және кестелердің құрылымы.', 'er_diagram.txt',
               'Кестелер: teachers, students, topics, applications, supervisor_requests, progress_files.\n', 5,
               'Кестелер арасындағы байланыстарды тексеріңіз.')

        self.stdout.write(self.style.SUCCESS(
            f'Дайын: {User.objects.filter(username__in=logins).count()} аккаунт, {Teacher.objects.count()} оқытушы, '
            f'{Student.objects.count()} студент, {Topic.objects.count()} тақырып, {Tag.objects.count()} тег. Құпия сөз: {PASSWORD}'))
