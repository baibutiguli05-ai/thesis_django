from django.contrib import admin

from .models import Application, ProgressFile, Student, SupervisorRequest, Tag, Teacher, Topic


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'academic_title', 'department', 'cs_quota', 'user')
    list_select_related = ('user',)
    search_fields = ('full_name', 'department')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'group_name', 'major', 'teacher', 'topic', 'user')
    list_select_related = ('teacher', 'topic', 'user')
    list_filter = ('major', 'teacher')
    search_fields = ('full_name', 'group_name')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'proposed_by', 'status', 'created_at')
    list_filter = ('status', 'proposed_by', 'teacher', 'tags')
    search_fields = ('title',)
    filter_horizontal = ('tags',)
    list_select_related = ('teacher',)


@admin.register(SupervisorRequest)
class SupervisorRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher', 'teacher_status', 'admin_status', 'created_at')
    list_select_related = ('student', 'teacher')
    list_filter = ('teacher_status', 'admin_status')


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('student', 'topic', 'teacher_status', 'admin_status', 'created_at')
    list_select_related = ('student', 'topic')
    list_filter = ('teacher_status', 'admin_status')


@admin.register(ProgressFile)
class ProgressFileAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'original_name', 'created_at')
    list_select_related = ('student',)
