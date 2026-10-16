from django import template
from django.utils.html import format_html, format_html_join

register = template.Library()

STATUS_LABELS = {'pending': 'Тексерілуде', 'approved': 'Бекітілді', 'rejected': 'Қабылданбады', 'taken': 'Таңдалған'}
ROLE_LABELS = {'admin': 'Әкімші', 'teacher': 'Оқытушы', 'student': 'Студент'}


@register.filter
def status_label(value):
    return STATUS_LABELS.get(value, value)


@register.filter
def role_label(value):
    return ROLE_LABELS.get(value, value)


@register.filter
def initials(name):
    parts = [p for p in str(name or '').split() if p]
    return ''.join(p[0].upper() for p in parts[:2]) or '?'


@register.filter
def first_name(name):
    parts = str(name or '').split()
    return parts[0] if parts else ''


@register.filter
def filesize(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ''
    if n <= 0:
        return ''
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{round(n / 1024)} KB'
    return f'{n / 1024 / 1024:.1f} MB'


@register.filter
def percent(part, whole):
    try:
        return min(100, round(int(part) / int(whole) * 100)) if int(whole) else 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 100


@register.simple_tag
def badge(status, label=None):
    return format_html('<span class="badge bg-{}">{}</span>', status, label or STATUS_LABELS.get(status, status))


@register.simple_tag
def chips(obj):
    """Оқытушы / әкімші шешімдерін көрсететін шағын белгілер."""
    icons = {'pending': 'fa-regular fa-clock', 'approved': 'fa-solid fa-check', 'rejected': 'fa-solid fa-xmark'}
    items = [(obj.teacher_status, 'Оқытушы'), (obj.admin_status, 'Әкімші')]
    inner = format_html_join('', '<span class="chip chip-{0}" title="{2}: {3}"><i class="{1}"></i>{2}</span>',
                             ((s, icons[s], who, STATUS_LABELS[s]) for s, who in items))
    return format_html('<span class="chips">{}</span>', inner)
