from django import forms
from app01.models import User, CaptchaModel
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError


# 注册专用
class RegisterForm(forms.Form):
    # 1. 用户名
    username = forms.CharField(
        max_length=20,
        min_length=2,
        error_messages={
            'required': '请输入用户名',
            'max_length': '用户名最多20个字符',
            'min_length': '用户名最少2个字符',
        }
    )

    # 2. 邮箱 - 放在验证码之前
    email = forms.EmailField(
        error_messages={
            'required': '请输入邮箱',
            'invalid': '请输入正确的邮箱格式',
        }
    )

    # 3. 验证码 - 这样验证时email已经存在
    captcha = forms.CharField(
        max_length=4,
        min_length=4,
        error_messages={
            'required': '请输入验证码',
            'max_length': '验证码必须4个字符',
            'min_length': '验证码必须4个字符',
        }
    )

    # 4. 密码
    password = forms.CharField(
        max_length=20,
        min_length=6,
        error_messages={
            'required': '请输入密码',
            'max_length': '密码最多20个字符',
            'min_length': '密码最少6个字符',
        },
        widget=forms.PasswordInput
    )

    # 5. 确认密码
    re_password = forms.CharField(
        max_length=20,
        min_length=6,
        error_messages={
            'required': '请输入确认密码',
            'max_length': '确认密码最多20个字符',
            'min_length': '确认密码最少6个字符',
        },
        widget=forms.PasswordInput
    )

    def clean_username(self):
        """验证用户名"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('用户名已存在')
        return username

    def clean_email(self):
        """验证邮箱"""
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError('邮箱不能为空')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('邮箱已存在')
        return email

    def clean_captcha(self):
        """验证验证码 - 现在可以获取到email"""
        captcha = self.cleaned_data.get('captcha')
        email = self.cleaned_data.get('email')

        print(f"验证验证码: captcha={captcha}, email={email}")

        if not captcha:
            raise forms.ValidationError('验证码不能为空')

        if not email:
            # 如果email还不存在，尝试从原始数据获取
            email = self.data.get('email')
            if not email:
                raise forms.ValidationError('邮箱不能为空')

        # 验证码校验
        if not CaptchaModel.objects.filter(captcha=captcha, email=email).exists():
            raise forms.ValidationError('验证码错误或已过期')

        # 验证通过后，删除验证码
        CaptchaModel.objects.filter(captcha=captcha, email=email).delete()

        return captcha

    def clean(self):
        """整体验证"""
        cleaned_data = super().clean()

        password = cleaned_data.get('password')
        re_password = cleaned_data.get('re_password')

        if password and re_password and password != re_password:
            self.add_error('re_password', '两次密码不一致')

        return cleaned_data


# 登录专用
class LoginForm(forms.Form):
    username_or_email = forms.CharField(
        max_length=254,  # 放宽
        min_length=2,
        error_messages={
            'required': '请输入用户名或邮箱',
            'max_length': '用户名或邮箱过长',
            'min_length': '用户名或邮箱最少2个字符',
        }
    )

    password = forms.CharField(
        max_length=20,
        min_length=6,
        error_messages={
            'required': '请输入密码',
            'max_length': '密码最多20个字符',
            'min_length': '密码最少6个字符',
        },
        widget=forms.PasswordInput
    )

    def clean_username_or_email(self):
        value = self.cleaned_data.get('username_or_email', '').strip()

        # 先尝试按邮箱校验格式
        is_email = True
        try:
            validate_email(value)
        except DjangoValidationError:
            is_email = False

        if is_email:
            if User.objects.filter(email=value).exists():
                return value
            raise forms.ValidationError('用户名或邮箱不存在')
        else:
            if User.objects.filter(username=value).exists():
                return value
            raise forms.ValidationError('用户名或邮箱不存在')
