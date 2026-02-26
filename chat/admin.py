from django.contrib import admin
from .models import User, Profile, Connection, Message


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class UserAdmin(admin.ModelAdmin):
    inlines = [ProfileInline]
    list_display = ['id', 'full_name', 'email', 'phone_number', 'kyc_status']


admin.site.register(User, UserAdmin)
admin.site.register(Profile)
admin.site.register(Connection)
admin.site.register(Message)