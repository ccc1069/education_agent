"""多租户行级隔离: SQLAlchemy event listener 自动注入 WHERE tenant_id。

设计:
- 维护"租户感知"ORM 类注册表(启动时扫描 db.models 收集)
- 监听 Session.do_orm_execute 事件
- 对每个注册类,加 with_loader_criteria 注入 WHERE tenant_id = :tid
- contextvar 为 None 时跳过(平台管理员跨租户操作)

启用:
- 在应用启动时调用 install_tenant_filter()
- 在测试中调用 uninstall_tenant_filter() 清理
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Mapper, Session, with_loader_criteria

from core.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)

_listener_installed = False
# 租户感知类注册表(运行时填充)
_tenant_aware_classes: list[type] = []


def _is_tenant_aware(mapper_cls: Any) -> bool:
    """检查类是否为带 tenant_id 列的 ORM 类。"""
    try:
        mapper = inspect(mapper_cls, raiseerr=False)
        if not isinstance(mapper, Mapper):
            return False
        return "tenant_id" in mapper.columns
    except Exception:
        return False


def register_tenant_aware_class(cls: type) -> None:
    """注册一个租户感知类。"""
    if cls not in _tenant_aware_classes:
        _tenant_aware_classes.append(cls)


def scan_and_register_all() -> None:
    """扫描 db.models 模块,注册所有带 tenant_id 列的 ORM 类。"""
    import db.models as models

    for name in dir(models):
        obj = getattr(models, name)
        if isinstance(obj, type) and _is_tenant_aware(obj):
            register_tenant_aware_class(obj)
    logger.info(
        "tenant_aware_classes_registered: count=%d",
        len(_tenant_aware_classes),
    )


def _do_orm_execute(orm_execute_state):
    """ORM 执行前钩子: 注入 with_loader_criteria(每类一条)。

    覆盖 SELECT / UPDATE / DELETE。
    """
    tid = get_tenant_id()
    if tid is None:
        return  # 跨租户(平台管理员)
    if not _tenant_aware_classes:
        return

    # 对每个租户感知类加过滤(with_loader_criteria 内部去重)
    # 用直接 SQL 表达式(非 lambda)避免 lambda 缓存 key 问题
    options = []
    for cls in _tenant_aware_classes:
        # cls.tenant_id == tid 直接构造 SQL 表达式,值在构造时绑定
        options.append(
            with_loader_criteria(
                cls,
                cls.tenant_id == tid,
                include_aliases=True,
            )
        )
    orm_execute_state.statement = orm_execute_state.statement.options(*options)


def install_tenant_filter() -> None:
    """安装租户过滤监听器(应用启动时调用)。"""
    global _listener_installed
    if _listener_installed:
        return

    scan_and_register_all()
    event.listen(Session, "do_orm_execute", _do_orm_execute)
    _listener_installed = True
    logger.info("tenant_filter_installed")


def uninstall_tenant_filter() -> None:
    """卸载监听器(测试用)。"""
    global _listener_installed
    if not _listener_installed:
        return
    try:
        event.remove(Session, "do_orm_execute", _do_orm_execute)
    except Exception:
        pass
    _tenant_aware_classes.clear()
    _listener_installed = False


def is_filter_installed() -> bool:
    """测试用: 检查监听器是否已安装。"""
    return _listener_installed


def get_tenant_aware_classes() -> list[type]:
    """测试用: 返回注册的类列表。"""
    return list(_tenant_aware_classes)


