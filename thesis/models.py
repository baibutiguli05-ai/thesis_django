from django.conf import settings
from django.db import models

STATUS_CHOICES = [('pending', 'Тексерілуде'), ('approved', 'Бекітілді'), ('rejected', 'Қабылданбады')]
TOPIC_STATUS = STATUS_CHOICES + [('taken', 'Таңдалған')]
MAJORS = [('CS', 'CS'), ('SE', 'SE'), ('IS', 'IS')]


def overall_status(teacher_status, admin_status):
    """Екі сатылы бекітудің қорытынды статусы: оқытушы + әкімші."""
    if 'rejected' in (teacher_status, admin_status):
        return 'rejected'
    if teacher_status == 'approved' and admin_status == 'approved':
        return 'approved'
    return 'pending'


class Teacher(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='teacher', verbose_name='Пайдаланушы')
    full_name = models.CharField('Аты-жөні', max_length=100)
    academic_title = models.CharField('Атағы', max_length=100, blank=True)
    department = models.CharField('Кафедра', max_length=150, blank=True)
    research_area = models.CharField('Ғылыми бағыты', max_length=255, blank=True)
    email = models.EmailField('Email', blank=True)
    cs_quota = models.PositiveIntegerField('CS квотасы', default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Оқытушы'
        verbose_name_plural = 'Оқытушылар'

    def __str__(self):
        return self.full_name

    @property
    def cs_taken(self):
        return self.students.filter(major='CS').count()

    @property
    def cs_remaining(self):
        return max(0, self.cs_quota - self.cs_taken)


class Tag(models.Model):
    """Тақырыптың кілт сөздері / бағыттары (Topic ↔ Tag: ManyToMany)."""
    name = models.CharField('Атауы', max_length=50, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Тег'
        verbose_name_plural = 'Тегтер'

    def __str__(self):
        return self.name


class Topic(models.Model):
    title = models.CharField('Тақырып атауы', max_length=255)
    description = models.TextField('Сипаттамасы', blank=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='topics', verbose_name='Оқытушы')
    proposed_by = models.CharField('Ұсынған', max_length=10, choices=[('teacher', 'Оқытушы'), ('student', 'Студент')], default='teacher')
    status = models.CharField('Статус', max_length=10, choices=TOPIC_STATUS, default='pending')
    tags = models.ManyToManyField(Tag, blank=True, related_name='topics', verbose_name='Тегтер')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'Тақырып'
        verbose_name_plural = 'Тақырыптар'
        constraints = [
            models.UniqueConstraint(fields=['teacher', 'title'], name='unique_topic_title_per_teacher'),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('topic_detail', args=[self.pk])


class Student(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='student', verbose_name='Пайдаланушы')
    full_name = models.CharField('Аты-жөні', max_length=100)
    group_name = models.CharField('Топ', max_length=30, blank=True)
    major = models.CharField('Мамандық', max_length=5, choices=MAJORS, default='CS')
    teacher = models.ForeignKey(Teacher, null=True, blank=True, on_delete=models.SET_NULL, related_name='students',
                                verbose_name='Бекітілген жетекші')
    topic = models.OneToOneField(Topic, null=True, blank=True, on_delete=models.SET_NULL, related_name='student',
                                 verbose_name='Бекітілген тақырып')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Студент'
        verbose_name_plural = 'Студенттер'

    def __str__(self):
        return self.full_name


class _TwoStep(models.Model):
    teacher_status = models.CharField('Оқытушы шешімі', max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_status = models.CharField('Әкімші шешімі', max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ['-id']

    @property
    def status(self):
        return overall_status(self.teacher_status, self.admin_status)


class SupervisorRequest(_TwoStep):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='supervisor_requests', verbose_name='Студент')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='supervisor_requests', verbose_name='Жетекші')
    message = models.TextField('Хабарлама', blank=True)

    class Meta(_TwoStep.Meta):
        verbose_name = 'Жетекші өтінімі'
        verbose_name_plural = 'Жетекші өтінімдері'

    def __str__(self):
        return f'{self.student} → {self.teacher}'


class Application(_TwoStep):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='applications', verbose_name='Студент')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='applications', verbose_name='Тақырып')

    class Meta(_TwoStep.Meta):
        verbose_name = 'Тақырып өтінімі'
        verbose_name_plural = 'Тақырып өтінімдері'

    def __str__(self):
        return f'{self.student} → {self.topic}'


def progress_upload_path(instance, filename):
    return f'progress/s{instance.student_id}/{filename}'


class ProgressFile(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='files', verbose_name='Студент')
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL, related_name='files')
    title = models.CharField('Кезең атауы', max_length=200)
    note = models.TextField('Түсініктеме', blank=True)
    file = models.FileField('Файл', upload_to=progress_upload_path, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    teacher_comment = models.TextField('Жетекші пікірі', blank=True)
    commented_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Жұмыс файлы'
        verbose_name_plural = 'Жұмыс файлдары'

    def __str__(self):
        return self.title

    @property
    def file_size(self):
        try:
            return self.file.size if self.file else 0
        except (OSError, ValueError):
            return 0
