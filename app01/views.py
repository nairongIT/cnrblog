# 标准库模块
import json
import hashlib
from datetime import date, timedelta
from uuid import uuid4

from django.contrib import auth
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden

from django.views import View

from app01.docorators import login
from app01.models import *  # noqa: F403
from app01.my_forms.article_forms import PubArticleForm
from app01.my_forms.user_forms import LoginForm, RegisterForm
from app01.utils.read_limiter import should_increase_read_count
from app01.utils.permissions import is_site_owner
from app01.utils.site_visit_limiter import should_count_site_visit


class IndexView(View):
    def get(self, request):
        # 搜索关键词（标题/正文）
        search_keyword = request.GET.get('q', '').strip()
        # 标签过滤参数
        tag_id = request.GET.get('tag', '').strip()

        # 文章基础查询：仅展示未删除且已发布的文章，按发布时间倒序
        article_queryset = Article.objects.filter(
            is_delete=False,
            status=1,
        ).select_related('user').order_by('-create_time')

        if search_keyword:
            article_queryset = article_queryset.filter(
                Q(title__icontains=search_keyword) | Q(content__icontains=search_keyword)
            )

        selected_tag = None
        if tag_id.isdigit():
            selected_tag = Tag.objects.filter(id=int(tag_id)).first()
            if selected_tag:
                article_queryset = article_queryset.filter(tags=selected_tag)

        # 多对多筛选后去重，避免同一文章重复显示
        article_queryset = article_queryset.distinct()

        # 热门标签：按关联文章数排序
        hot_tags = Tag.objects.annotate(
            article_total=Count(
                'articles',
                filter=Q(articles__is_delete=False, articles__status=1),
                distinct=True,
            )
        ).filter(article_total__gt=0).order_by('-article_total', 'name')[:12]

        # 热门文章 Top5：按 read_count + comment_count * 2 排序
        hot_articles = Article.objects.filter(
            is_delete=False,
            status=1,
        ).annotate(
            hot_score=ExpressionWrapper(
                F('read_count') + F('comment_count') * 2,
                output_field=IntegerField(),
            )
        ).order_by('-hot_score', '-create_time')[:5]

        # 站点统计
        article_total = Article.objects.filter(is_delete=False, status=1).count()
        user_total = User.objects.count()
        today = date.today()
        today_visit_obj, _ = DailyVisitStat.objects.get_or_create(date=today)
        # 临时性能排查：注释 Redis 去重，直接计数
        # if should_count_site_visit(request):
        #     DailyVisitStat.objects.filter(id=today_visit_obj.id).update(visit_count=F('visit_count') + 1)
        DailyVisitStat.objects.filter(id=today_visit_obj.id).update(visit_count=F('visit_count') + 1)
        today_visit_obj.refresh_from_db(fields=['visit_count'])
        today_visit_count = today_visit_obj.visit_count
        total_visit_count = DailyVisitStat.objects.aggregate(total=Sum('visit_count'))['total'] or 0

        # Paginator：分页器，每页 6 条
        paginator = Paginator(article_queryset, 6)
        # GET 参数 page 指定页码，不合法时自动回退为第一页
        page_obj = paginator.get_page(request.GET.get('page', 1))

        # 分页时保留除 page 之外的查询参数（如 q/tag）
        query_params = request.GET.copy()
        query_params.pop('page', None)
        querystring = query_params.urlencode()

        return render(request, 'index.html', locals())


class ArticleDetailView(View):
    @staticmethod
    def _get_article(article_id):
        # 统一封装文章查询条件：仅允许查看未删除且已发布的文章
        return get_object_or_404(
            Article.objects.select_related('user').prefetch_related('tags'),
            id=article_id,
            is_delete=False,
            status=1,
        )

    @staticmethod
    def _get_comment_queryset(article):
        # 反向外键 article.comments 获取评论；
        # select_related 预取 user/parent/root，减少模板里访问关联字段时的 SQL 次数
        return article.comments.select_related('user', 'parent__user', 'root').order_by('create_time')

    @staticmethod
    def _build_comment_tree(comment_queryset):
        # 按“根评论 -> 子评论列表”组织数据，便于模板按楼层折叠显示
        comment_list = list(comment_queryset)
        root_comments = []
        replies_by_root = {}

        for comment in comment_list:
            if comment.parent_id is None and comment.depth == 0:
                root_comments.append(comment)
                replies_by_root[comment.id] = []

        for comment in comment_list:
            if comment.parent_id is None and comment.depth == 0:
                continue
            root_id = comment.root_id or comment.parent_id
            if root_id in replies_by_root:
                replies_by_root[root_id].append(comment)

        root_comment_items = []
        for root in root_comments:
            root_comment_items.append({
                'root': root,
                'replies': replies_by_root.get(root.id, []),
            })
        return root_comment_items

    @staticmethod
    def _get_or_create_guest_user(request, guest_name):
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '') or request.META.get('REMOTE_ADDR', '')
        raw = f"{ip}|{guest_name}"
        uid = hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]
        username = f"guest_{uid}"
        guest_user = User.objects.filter(username=username).first()
        if guest_user:
            if guest_user.first_name != guest_name:
                guest_user.first_name = guest_name
                guest_user.save(update_fields=['first_name'])
            return guest_user

        guest_user = User(username=username, first_name=guest_name)
        guest_user.set_unusable_password()
        guest_user.save()
        return guest_user

    def get(self, request, article_id):
        article = self._get_article(article_id)
        # 临时性能排查：注释 Redis 去重，直接计数
        # if should_increase_read_count(request, article.id):
        #     Article.objects.filter(id=article.id).update(read_count=F('read_count') + 1)
        Article.objects.filter(id=article.id).update(read_count=F('read_count') + 1)
        # refresh_from_db：把内存中的 article 字段刷新为数据库最新值
        article.refresh_from_db(fields=['read_count'])
        comment_queryset = self._get_comment_queryset(article)
        root_comment_items = self._build_comment_tree(comment_queryset)
        return render(request, 'article_detail.html', locals())

    def post(self, request, article_id):
        article = self._get_article(article_id)
        # 去除首尾空格，防止纯空白评论
        content = request.POST.get('content', '').strip()
        parent_id = request.POST.get('parent_id', '').strip()
        guest_name = request.POST.get('guest_name', '').strip()
        if not content:
            comment_error = '评论内容不能为空'
            comment_queryset = self._get_comment_queryset(article)
            root_comment_items = self._build_comment_tree(comment_queryset)
            return render(request, 'article_detail.html', locals())

        if request.user.is_authenticated:
            comment_user = request.user
        else:
            if not guest_name:
                comment_error = '游客评论请先填写昵称'
                comment_queryset = self._get_comment_queryset(article)
                root_comment_items = self._build_comment_tree(comment_queryset)
                return render(request, 'article_detail.html', locals())
            if len(guest_name) > 20:
                comment_error = '昵称不能超过 20 个字符'
                comment_queryset = self._get_comment_queryset(article)
                root_comment_items = self._build_comment_tree(comment_queryset)
                return render(request, 'article_detail.html', locals())
            comment_user = self._get_or_create_guest_user(request, guest_name)

        parent_comment = None
        root_comment = None
        depth = 0
        if parent_id:
            # 仅允许回复当前文章下的评论，防止越权关联
            parent_comment = article.comments.filter(id=parent_id).first()
            if not parent_comment:
                comment_error = '回复目标评论不存在'
                comment_queryset = self._get_comment_queryset(article)
                root_comment_items = self._build_comment_tree(comment_queryset)
                return render(request, 'article_detail.html', locals())

            # 若父评论本身就是回复，则继承其根评论；否则父评论即根评论
            root_comment = parent_comment.root if parent_comment.root_id else parent_comment
            depth = parent_comment.depth + 1

        Comment.objects.create(
            article=article,
            user=comment_user,
            content=content,
            parent=parent_comment,
            root=root_comment,
            depth=depth,
        )
        # 新增评论后同步更新文章评论计数
        Article.objects.filter(id=article.id).update(comment_count=F('comment_count') + 1)
        return redirect('article_detail', article_id=article.id)

    def http_method_not_allowed(self, request, *args, **kwargs):
        # 明确返回 JSON，便于前端识别非法请求方法
        return JsonResponse({'code': 405, 'msg': '请求方法不被允许'})


class PubArticleView(View):
    @login.is_login_method
    def get(self, request):
        if not is_site_owner(request.user):
            return HttpResponseForbidden("无权限访问发布页面")
        # 展示发布页时读取所有标签供勾选
        tags = Tag.objects.all()
        return render(request, 'pub_article.html', locals())

    @login.is_login_method
    def post(self, request):
        if not is_site_owner(request.user):
            return JsonResponse({'code': 403, 'msg': '无权限发布文章'})
        # 使用自定义表单类做字段校验（长度、必填、类型等）
        print(request.POST)
        pub_article_form = PubArticleForm(request.POST)
        if not pub_article_form.is_valid():
            return JsonResponse({'code': 400, 'msg': pub_article_form.errors})

        # cleaned_data：读取表单校验通过后的安全数据
        title = pub_article_form.cleaned_data['title']
        content = pub_article_form.cleaned_data['content']
        tags = pub_article_form.cleaned_data['tags']
        user = request.user
        # create：创建文章记录
        article = Article.objects.create(
            title=title,
            content=content,
            user=user,
        )
        # many-to-many 关系赋值（文章-标签）
        article.tags.set(tags)

        return JsonResponse({'code': 200, 'msg': '文章发布成功!'})


class EditArticleView(View):
    @staticmethod
    def _get_my_article(request, article_id):
        # 仅允许作者编辑自己的未删除文章
        return get_object_or_404(
            Article.objects.prefetch_related('tags'),
            id=article_id,
            user=request.user,
            is_delete=False,
        )

    @login.is_login_method
    def get(self, request, article_id):
        if not is_site_owner(request.user):
            return HttpResponseForbidden("无权限编辑文章")
        article = self._get_my_article(request, article_id)
        tags = Tag.objects.all().order_by('name')
        selected_tag_ids = list(article.tags.values_list('id', flat=True))
        return render(request, 'article_edit.html', locals())

    @login.is_login_method
    def post(self, request, article_id):
        if not is_site_owner(request.user):
            return JsonResponse({'code': 403, 'msg': '无权限编辑文章'})
        article = self._get_my_article(request, article_id)
        edit_form = PubArticleForm(request.POST)
        if not edit_form.is_valid():
            return JsonResponse({'code': 400, 'msg': edit_form.errors})

        article.title = edit_form.cleaned_data['title']
        article.content = edit_form.cleaned_data['content']
        article.save(update_fields=['title', 'content', 'update_time'])
        article.tags.set(edit_form.cleaned_data['tags'])

        return JsonResponse({'code': 200, 'msg': '文章更新成功!'})


class DeleteArticleView(View):
    @login.is_login_method
    def post(self, request, article_id):
        if not is_site_owner(request.user):
            return JsonResponse({'code': 403, 'msg': '无权限删除文章'})

        article = get_object_or_404(
            Article,
            id=article_id,
            user=request.user,
            is_delete=False,
        )
        # 逻辑删除
        article.is_delete = True
        article.save(update_fields=['is_delete', 'update_time'])
        return redirect('index')


class LoginView(View):
    def get(self, request):
        return render(request, 'login.html', locals())

    def post(self, request):
        remember = request.POST.get('remenber')
        # 登录表单校验（用户名/邮箱、密码格式）
        login_form = LoginForm(request.POST)
        if not login_form.is_valid():
            return JsonResponse({'code': 400, 'msg': login_form.errors})

        # 先按用户名查，不存在再按邮箱查
        username_or_email = login_form.cleaned_data['username_or_email']
        password = login_form.cleaned_data['password']
        user = User.objects.filter(username=username_or_email).first()
        if not user:
            user = User.objects.filter(email=username_or_email).first()
        if not user:
            return JsonResponse({'code': 400, 'msg': {'username_or_email': ['账号或邮箱错误']}})
        if not user.check_password(password):
            return JsonResponse({'code': 400, 'msg': {'password': ['密码错误']}})

        # auth.login：把用户写入 session，建立登录态
        # session.set_expiry：设置 session 过期策略
        if remember:
            # 7 天后过期
            request.session.set_expiry(60 * 60 * 24 * 7)
        else:
            # 浏览器关闭即过期
            request.session.set_expiry(0)

        auth.login(request, user)

        return JsonResponse({'code': 200, 'msg': '登录成功!'})


class RegisterView(View):
    def get(self, request):
        return render(request, 'register.html', locals())

    def post(self, request):
        # 注册表单校验（用户名、邮箱、验证码、两次密码）
        register_form = RegisterForm(request.POST)
        if not register_form.is_valid():
            return JsonResponse({'code': 400, 'msg': register_form.errors})
        email = register_form.cleaned_data['email']
        password = register_form.cleaned_data['password']
        username = register_form.cleaned_data['username']
        # create_user：会自动哈希密码；create 不会哈希密码
        User.objects.create_user(username=username, email=email, password=password)

        return JsonResponse({'code': 200, 'msg': '注册成功!'})


class PersonalCenterView(View):
    @staticmethod
    def _build_context(request):
        # 个人中心仅展示当前登录用户自己的已发布文章
        my_articles = Article.objects.filter(
            user=request.user,
            is_delete=False,
            status=1,
        ).order_by('-create_time')
        my_article_total = my_articles.count()
        my_read_total = my_articles.aggregate(total=Sum('read_count'))['total'] or 0
        my_comment_total = my_articles.aggregate(total=Sum('comment_count'))['total'] or 0
        all_tags = Tag.objects.annotate(article_total=Count('articles', distinct=True)).order_by('name')
        # 互动通知：
        # 1) 他人评论了我的文章
        # 2) 他人回复了我的评论
        notification_queryset = Comment.objects.select_related(
            'user', 'article', 'parent__user'
        ).filter(
            Q(article__user=request.user) | Q(parent__user=request.user)
        ).exclude(
            user=request.user
        ).order_by('-create_time')[:20]
        return {
            'my_articles': my_articles,
            'my_article_total': my_article_total,
            'my_read_total': my_read_total,
            'my_comment_total': my_comment_total,
            'all_tags': all_tags,
            'notification_queryset': notification_queryset,
        }

    @login.is_login_method
    def get(self, request):
        context = self._build_context(request)
        return render(request, 'profile.html', context)

    @login.is_login_method
    def post(self, request):
        profile_success = ''
        profile_error = ''
        action = request.POST.get('action', '').strip()

        if action == 'avatar':
            avatar_file = request.FILES.get('avatar')
            if not avatar_file:
                profile_error = '请选择头像文件'
            else:
                allow_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                file_name = avatar_file.name or ''
                dot_index = file_name.rfind('.')
                ext = file_name[dot_index:].lower() if dot_index >= 0 else ''
                if ext not in allow_ext:
                    profile_error = '头像仅支持 jpg/jpeg/png/gif/webp'
                elif avatar_file.size > 5 * 1024 * 1024:
                    profile_error = '头像大小不能超过 5MB'
                else:
                    request.user.avatar = avatar_file
                    request.user.save(update_fields=['avatar'])
                    profile_success = '头像更新成功'
        elif action == 'tag_add':
            if not is_site_owner(request.user):
                profile_error = '无权限新增标签'
            else:
                tag_name = request.POST.get('tag_name', '').strip()
                if not tag_name:
                    profile_error = '标签名不能为空'
                elif len(tag_name) > 32:
                    profile_error = '标签名不能超过 32 个字符'
                else:
                    _, created = Tag.objects.get_or_create(name=tag_name)
                    if created:
                        profile_success = '标签添加成功'
                    else:
                        profile_error = '标签已存在'
        elif action == 'tag_delete':
            if not is_site_owner(request.user):
                profile_error = '无权限删除标签'
            else:
                tag_id = request.POST.get('tag_id', '').strip()
                if not tag_id.isdigit():
                    profile_error = '标签参数错误'
                else:
                    tag_obj = Tag.objects.filter(id=int(tag_id)).first()
                    if not tag_obj:
                        profile_error = '标签不存在'
                    else:
                        tag_obj.delete()
                        profile_success = '标签删除成功'
        else:
            profile_error = '无效操作'

        context = self._build_context(request)
        context['profile_success'] = profile_success
        context['profile_error'] = profile_error
        return render(request, 'profile.html', context)


class DataDashboardView(View):
    def get(self, request):
        # 最近 14 天访问趋势
        days = 14
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        stat_queryset = DailyVisitStat.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
        ).values('date', 'visit_count')
        stat_map = {item['date']: item['visit_count'] for item in stat_queryset}

        visit_dates = []
        visit_values = []
        visit_cumulative_values = []
        cumulative = 0
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            day_value = int(stat_map.get(current_date, 0))
            cumulative += day_value
            visit_dates.append(current_date.strftime('%m-%d'))
            visit_values.append(day_value)
            visit_cumulative_values.append(cumulative)

        # 最近 14 天注册趋势
        register_queryset = User.objects.filter(
            date_joined__date__gte=start_date,
            date_joined__date__lte=end_date,
        ).annotate(
            register_date=TruncDate('date_joined')
        ).values(
            'register_date'
        ).annotate(
            total=Count('id')
        )
        register_map = {item['register_date']: item['total'] for item in register_queryset}
        register_values = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            register_values.append(int(register_map.get(current_date, 0)))

        visit_dates_json = json.dumps(visit_dates, ensure_ascii=False)
        visit_values_json = json.dumps(visit_values, ensure_ascii=False)
        visit_cumulative_values_json = json.dumps(visit_cumulative_values, ensure_ascii=False)
        register_values_json = json.dumps(register_values, ensure_ascii=False)
        total_visit_count = DailyVisitStat.objects.aggregate(total=Sum('visit_count'))['total'] or 0
        total_user_count = User.objects.count()
        return render(request, 'dashboard.html', locals())


# 退出登录
@login.is_login_func
def logout(request):
    if request.method == 'POST':
        # auth.logout：清空当前登录态（session）
        auth.logout(request)
        return JsonResponse({'code': 200, 'msg': '退出登录成功!'})

    return JsonResponse({'code': 400, 'msg': '请求方法错误!'})


@login.is_login_func
def upload_article_image(request):
    if request.method != 'POST':
        return JsonResponse({'success': 0, 'message': '仅支持 POST 请求'})

    image_file = request.FILES.get('editormd-image-file')
    if not image_file:
        return JsonResponse({'success': 0, 'message': '未接收到图片文件'})

    allow_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    file_name = image_file.name or ''
    dot_index = file_name.rfind('.')
    ext = file_name[dot_index:].lower() if dot_index >= 0 else ''
    if ext not in allow_ext:
        return JsonResponse({'success': 0, 'message': '仅支持 jpg/jpeg/png/gif/webp'})

    # 10MB 限制
    if image_file.size > 10 * 1024 * 1024:
        return JsonResponse({'success': 0, 'message': '图片大小不能超过 10MB'})

    # 保存到 media/article/
    safe_name = f"{uuid4().hex}{ext}"
    save_path = default_storage.save(f"article/{safe_name}", image_file)
    file_url = f"{settings.MEDIA_URL}{save_path}".replace('\\', '/')
    return JsonResponse({'success': 1, 'message': '上传成功', 'url': file_url})


@login.is_login_func
def create_tag(request):
    if not is_site_owner(request.user):
        return JsonResponse({'code': 403, 'msg': '无权限管理标签'})

    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': '仅支持 POST 请求'})

    tag_name = request.POST.get('name', '').strip()
    if not tag_name:
        return JsonResponse({'code': 400, 'msg': '标签名不能为空'})

    if len(tag_name) > 32:
        return JsonResponse({'code': 400, 'msg': '标签名不能超过 32 个字符'})

    tag_obj, created = Tag.objects.get_or_create(name=tag_name)
    if not created:
        return JsonResponse({'code': 400, 'msg': '标签已存在'})

    return JsonResponse({
        'code': 200,
        'msg': '添加成功',
        'data': {
            'id': tag_obj.id,
            'name': tag_obj.name,
        }
    })




