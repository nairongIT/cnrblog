from django.contrib.auth.models import AbstractUser
from django.db import models


# 抽象类，用于定义公共字段
class CommonModel(models.Model):
    create_time = models.DateTimeField(auto_now_add=True)  # 创建时间
    update_time = models.DateTimeField(auto_now=True)  # 更新时间

    class Meta:
        abstract = True  # 抽象类，不创建数据库表


# 验证码表
class CaptchaModel(models.Model):
    email = models.EmailField(unique=True)  # 邮箱
    captcha = models.CharField(max_length=4)  # 验证码
    create_time = models.DateTimeField(auto_now_add=True)


# 用户表
class User(AbstractUser):
    class Meta:
        verbose_name = "user"
        verbose_name_plural = "user"
    # 重写你不想要的字段，设置为允许为空
    last_name = models.CharField(max_length=150, blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True, null=True)

    # 头像
    avatar = models.FileField(upload_to='avatar/', default="avatar/default.webp", blank=True, null=True)

    def __str__(self):
        return self.username

# 标签表
class Tag(CommonModel):
    name = models.CharField("标签名", max_length=32, unique=True)


    def __str__(self):
        return self.name

# 评论表
class Comment(CommonModel):
    # 评论文章
    article = models.ForeignKey(
        to='Article',
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="文章",
    )
    # 评论用户
    user = models.ForeignKey(
        User,
        related_name="comments",
        on_delete=models.CASCADE,
        verbose_name="用户",
    )
    # 评论内容
    content = models.TextField("评论内容")

    # 根评论
    root = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        blank=True,
        null=True,
        verbose_name="根评论",
    )
    # 回复评论
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
        verbose_name="回复评论",
    )
    # 深度 表示评论的层级，根评论深度为0，回复评论深度为1
    depth = models.PositiveIntegerField("深度", default=0)


    def __str__(self):
        return self.content[:10]
# 文章表
class Article(CommonModel):
    STATUS_CHOICES = (
        (0, "草稿"),
        (1, "已发布"),
    )

    title = models.CharField(max_length=255)  # 标题
    content = models.TextField()  # 内容
    status = models.SmallIntegerField("状态", choices=STATUS_CHOICES, default=1)
    is_delete = models.BooleanField("是否删除", default=False)  # 逻辑删除
    is_top = models.BooleanField("是否置顶", default=False)  # 是否置顶

    # 计数器（优化查询）
    # 阅读量
    read_count = models.PositiveIntegerField("阅读量", default=0)
    # 评论量
    comment_count = models.PositiveIntegerField("评论量", default=0)

    # 外键关系
    user = models.ForeignKey(
        User,
        related_name="articles",
        on_delete=models.CASCADE,
        verbose_name="作者",
    )
    tags = models.ManyToManyField(
        Tag,
        related_name="articles",
        blank=True,
        verbose_name="标签",
    )

    def __str__(self):
        return self.title


class DailyVisitStat(models.Model):
    # 每天一条访问统计记录
    date = models.DateField(unique=True)
    # 当天访问量（按首页请求次数累计）
    visit_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "daily_visit_stat"
        verbose_name_plural = "daily_visit_stat"

    def __str__(self):
        return f"{self.date}: {self.visit_count}"

