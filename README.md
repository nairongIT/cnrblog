# CNR Blog（个人博客系统）

## 项目概述
CNR Blog 是一个基于 Django 的个人博客系统，核心目标是：
- 站长（超级管理员）负责内容生产与管理；
- 普通用户与游客可以阅读并参与互动；
- 提供基础统计与可视化数据看板。

当前项目已达到“可上线的个人博客 MVP”阶段。

---

## 技术栈
- Python 3.12
- Django 4.2
- MySQL
- Redis（阅读量/访问量去重）
- Bootstrap + jQuery
- editor.md（Markdown 编辑器）
- ECharts（本地静态引入）

---

## 功能清单

### 1) 用户与权限
- 注册 / 登录 / 退出
- 个人中心（头像更新、我的文章、互动通知）
- 权限规则：
  - 仅站长（`is_superuser=True`）可：发布文章、编辑文章、删除文章、管理标签
  - 普通用户可：浏览文章、评论、回复
  - 游客可：浏览文章、评论、回复、查看数据分析

### 2) 文章系统
- 发布文章（Markdown）
- 编辑文章（标题/内容/标签）
- 删除文章（逻辑删除：`is_delete=True`）
- 文章详情渲染 Markdown
- 详情页作者可见“编辑/删除”按钮（且需站长权限）

### 3) 标签系统
- 发布页可选标签
- 支持新增标签（弹窗）
- 个人中心支持标签新增/删除（仅站长）

### 4) 评论与回复
- 评论发布
- 回复评论（root/parent/depth）
- 根评论可展开查看全部子回复
- 游客评论：
  - 未登录用户可评论/回复
  - 必填“昵称”
- 个人中心互动通知：
  - 他人评论我的文章
  - 他人回复我的评论

### 5) 图片上传（本地）
- 发布/编辑页支持本地上传图片
- 上传成功自动将 Markdown 图片语法插入正文末尾
- 文件存储：`media/article/`
- 文件名：UUID 随机命名
- 格式限制：`jpg/jpeg/png/gif/webp`
- 大小限制：10MB

### 6) 首页能力
- 分页（每页 6 篇）
- 搜索（标题 + 正文）
- 热门标签过滤
- 热门文章 Top5
- 网站信息（文章总数、注册用户数、今日访问、总访问）

---

## 关键业务规则

### 热度值公式（热门文章排序）

```text
hot_score = read_count + comment_count * 2
```

说明：
- 评论权重为 2，互动质量影响更大。
- 热度相同按发布时间倒序。

### 阅读量防刷（文章详情）
- 登录用户：`user_id + article_id`，1 小时内只记 1 次
- 匿名用户：`IP + User-Agent + article_id`，1 小时内只记 1 次
- Redis 不可用时自动降级 session 去重

### 访问量防刷（首页）
- 今日访问：按 `IP` 1 小时去重计数
- 总访问量：`DailyVisitStat.visit_count` 累计
- Redis 不可用时自动降级 session 去重

---

## 数据分析看板
路径：`/dashboard/`

访问权限：
- 已开放给所有访问者（包括游客）

当前图表：
1. 最近 14 天访问趋势（双线同图）
   - 当日访问
   - 累计访问
2. 最近 14 天注册用户趋势

ECharts 使用方式：
- 本地静态文件导入（当前已使用）
- 文件：`static/js/echarts.min.js`

---

## 目录结构（核心）

```text
blog/
├─ app01/
│  ├─ models.py
│  ├─ views.py
│  ├─ urls.py
│  ├─ my_forms/
│  └─ utils/
│     ├─ permissions.py
│     ├─ read_limiter.py
│     └─ site_visit_limiter.py
├─ blog/
│  └─ settings.py
├─ templates/
│  ├─ index.html
│  ├─ article_detail.html
│  ├─ pub_article.html
│  ├─ article_edit.html
│  ├─ profile.html
│  └─ dashboard.html
├─ static/
├─ media/
└─ manage.py
```

---

## 本地运行

1. 安装依赖
2. 执行迁移

```bash
python manage.py migrate
```

3. 启动服务

```bash
python manage.py runserver
```

---

## 配置项（当前）
- Redis
  - `REDIS_HOST=127.0.0.1`
  - `REDIS_PORT=6379`
  - `REDIS_DB=0`
  - `REDIS_PASSWORD=123456`
- 去重窗口
  - `ARTICLE_READ_LIMIT_SECONDS=3600`
  - `SITE_VISIT_LIMIT_SECONDS=3600`

> 建议上线时把密码和密钥迁移到环境变量。

---

## 上线流程（Nginx + uWSGI）

### 1. 上线前
1. `DEBUG=False`
2. 配置 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`
3. 准备 MySQL、Redis、Python 环境
4. 使用环境变量管理敏感信息

### 2. 部署
1. 安装依赖
2. `python manage.py migrate`
3. `python manage.py collectstatic --noinput`
4. 启动 uWSGI（建议 Unix Socket）
5. Nginx 反代 uWSGI，并映射：
   - `/static/`
   - `/media/`
6. 配置 HTTPS 证书

### 3. 运行保障
1. 使用 systemd/supervisor 守护 uWSGI
2. 配置日志轮转
3. 做数据库 + 媒体文件备份

---

## 后续优化建议

### 安全
1. 上传文件增加真实图片校验（Pillow）与像素上限。
2. 图片上传接口补充频率限制与审计日志。
3. 将敏感配置（数据库/邮箱/Redis）迁移环境变量。

### 性能
1. 热门文章/热门标签查询加缓存。
2. 评论列表做分页加载（大数据量优化）。

### 产品体验
1. 通知增加“已读/未读”状态。
2. 增加文章草稿箱与回收站。
3. 看板新增 Top 文章、标签分布等图表。

---

## 总结
当前版本已经具备个人博客核心闭环：
- 内容生产（发布/编辑/删除）
- 用户互动（评论/回复/通知，含游客昵称评论）
- 数据统计（访问、注册、可视化看板）
- 权限边界（站长管理、普通用户与游客互动）

可以作为上线基础版本，后续重点是安全加固、运行稳定和数据深化。
