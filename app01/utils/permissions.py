def is_site_owner(user):
    """站点内容管理权限：当前默认仅超级管理员可管理内容。"""
    return bool(user and user.is_authenticated and user.is_superuser)

