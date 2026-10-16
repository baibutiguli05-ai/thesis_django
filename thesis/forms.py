import re

from django import forms
from django.contrib.auth.models import User

from .models import Student, Tag, Teacher, Topic


class RegisterForm(forms.Form):
    full_name = forms.CharField(label='Аты-жөні', max_length=100)
    username = forms.CharField(label='Логин', max_length=50)
    password = forms.CharField(label='Құпия сөз', widget=forms.PasswordInput)
    role = forms.ChoiceField(label='Рөлі', choices=[('student', 'Студент'), ('teacher', 'Оқытушы')], initial='student')

    def clean_username(self):
        u = self.cleaned_data['username'].strip()
        if not re.fullmatch(r'[\w.@+-]+', u):
            raise forms.ValidationError('Логинде тек әріптер, сандар және . @ + - _ таңбалары болуы мүмкін.')
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError('Бұл логин бос емес!')
        return u

    def clean_password(self):
        p = self.cleaned_data['password']
        if len(p) < 6 or not re.search(r'[A-Za-z]', p) or not re.search(r'\d', p):
            raise forms.ValidationError('Құпия сөз кемінде 6 таңбадан тұруы керек, әрі әріптер мен сандардан құралуы тиіс!')
        return p


class _Styled(forms.ModelForm):
    """Барлық өрістерге ортақ .input стилін қосады."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'input')


class TeacherForm(_Styled):
    class Meta:
        model = Teacher
        fields = ['full_name', 'academic_title', 'department', 'research_area', 'email', 'cs_quota', 'user']


class StudentForm(_Styled):
    class Meta:
        model = Student
        fields = ['full_name', 'group_name', 'major', 'teacher', 'topic', 'user']


class TopicForm(_Styled):
    class Meta:
        model = Topic
        fields = ['title', 'description', 'teacher', 'proposed_by', 'status']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class TopicCrudForm(_Styled):
    """Тақырыпты жасау / өңдеу формасы (CBV). Валидация серверде орындалады."""

    class Meta:
        model = Topic
        fields = ['title', 'description', 'tags', 'teacher', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'tags': forms.CheckboxSelectMultiple,
        }
        help_texts = {'tags': 'Ең көбі 5 тег таңдаңыз.'}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['tags'].widget.attrs.pop('class', None)
        self.fields['tags'].queryset = Tag.objects.order_by('name')
        if not (user and user.is_staff):
            # Оқытушы тақырыптың иесін де, статусын да өзі таңдамайды
            del self.fields['teacher']
            del self.fields['status']
        else:
            self.fields['status'].choices = [c for c in self.fields['status'].choices if c[0] != 'taken'] \
                if not (self.instance.pk and self.instance.status == 'taken') else self.fields['status'].choices

    def _owner(self):
        if 'teacher' in self.fields:
            return self.cleaned_data.get('teacher')
        if self.instance.pk:
            return self.instance.teacher
        return getattr(self.user, 'teacher', None)

    def clean_title(self):
        title = ' '.join(self.cleaned_data['title'].split())
        if len(title) < 10:
            raise forms.ValidationError('Тақырып атауы кемінде 10 таңбадан тұруы керек.')
        if title.replace(' ', '').isdigit():
            raise forms.ValidationError('Тақырып атауы тек сандардан тұрмауы керек.')
        return title

    def clean_description(self):
        d = self.cleaned_data.get('description', '').strip()
        if d and len(d) < 20:
            raise forms.ValidationError('Сипаттама кемінде 20 таңбадан тұруы керек (немесе бос қалдырыңыз).')
        return d

    def clean_tags(self):
        tags = self.cleaned_data.get('tags')
        if tags is not None and len(tags) > 5:
            raise forms.ValidationError('Ең көбі 5 тег таңдауға болады.')
        return tags

    def clean(self):
        data = super().clean()
        title, owner = data.get('title'), self._owner()
        if title and owner:
            # Регистрге тәуелсіз салыстыру Python-да (қазақ әріптері кез келген дерекқорда дұрыс салыстырылады)
            others = Topic.objects.filter(teacher=owner).exclude(pk=self.instance.pk).values_list('title', flat=True)
            if title.casefold() in {t.casefold() for t in others}:
                self.add_error('title', 'Бұл оқытушыда осындай атаулы тақырып бар.')
        return data
