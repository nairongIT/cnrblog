# 导入forms模块
from django import forms

from app01.models import Tag


class PubArticleForm(forms.Form):
    title = forms.CharField(max_length=32, min_length=1, error_messages={
        'max_length': '标题最多32个字符',
        'min_length': '标题最少3个字符',
        'required': '请输入标题',
    })
    content = forms.CharField(max_length=1024, min_length=1, error_messages={
        'max_length': '内容最多1024个字符',
        'min_length': '内容最少10个字符',
        'required': '请输入内容',
    })
    # 可以用ModelMultipleChoiceField来选择多个标签
    tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.all(), error_messages={
        'required': '请选择标签',
    })
