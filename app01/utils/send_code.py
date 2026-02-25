from app01.models import CaptchaModel # 验证码表
from django.http import JsonResponse
from django.core.mail import send_mail  # django自带的发送邮件模块
import random

def send_email_captcha(request):
    # ?email=xxx
    email = request.GET.get('email')
    if not email:
        return JsonResponse({'code': 400, 'msg': '必须传递邮箱!'})
    # 生成验证码（取4位随机数）
    captcha = str(random.randint(1000, 9999))
    # 后续优化到redis缓存，这里先简单存储到mysql数据库
    """
        如果数据库中已经存在该邮箱的验证码，那么就更新验证码，否则就创建新的验证码
    """
    try:
        captcha_model = CaptchaModel.objects.get(email=email)
        captcha_model.captcha = captcha
        captcha_model.save()
    except CaptchaModel.DoesNotExist:
        CaptchaModel.objects.create(email=email, captcha=captcha)

    request.session['email_captcha'] = captcha

    """
        参数解释
        1. 邮件标题
        2. 邮件内容
        3. recipient_list 收件人列表（该列表可以同时发送给多个收件人）
        4. from_email 发件人邮箱（默认是settings.EMAIL_HOST_USER）,由于没有默认值参数，需要设置None，自动使用settings.EMAIL_HOST_USER
    """
    send_mail("乃荣博客注册验证码", captcha, recipient_list=[email], fail_silently=False, from_email=None)
    print('成功发送邮箱:', captcha)
    return JsonResponse({'code': 200, 'msg': '验证码发送成功!'})
