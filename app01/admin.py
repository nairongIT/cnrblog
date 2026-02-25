from django.contrib import admin
from app01.models import *
# 注册模型类
admin.site.register(User)
admin.site.register(Article)
admin.site.register(Comment)
admin.site.register(Tag)


