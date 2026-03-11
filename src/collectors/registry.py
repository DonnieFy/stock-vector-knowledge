"""采集器插件注册表"""

from typing import Type

_registry: dict[str, Type] = {}


def register_collector(cls):
    """
    采集器注册装饰器。

    用法:
        @register_collector
        class MyCollector(BaseCollector):
            name = "my_source"
            ...
    """
    if not hasattr(cls, "name") or not cls.name:
        raise ValueError(f"采集器 {cls.__name__} 必须定义 name 属性")
    _registry[cls.name] = cls
    return cls


def get_collector(name: str):
    """获取采集器实例"""
    if name not in _registry:
        available = ", ".join(_registry.keys())
        raise KeyError(f"未找到采集器 '{name}'，可用采集器: {available}")
    return _registry[name]()


def get_all_collectors(enabled_only: bool = True):
    """获取所有采集器实例"""
    if enabled_only:
        from src.config import get_config
        config = get_config()
        enabled = config.enabled_collectors
        return [_registry[name]() for name in enabled if name in _registry]
    return [cls() for cls in _registry.values()]


def list_collectors() -> list[dict]:
    """列出所有已注册的采集器信息"""
    return [
        {"name": name, "description": getattr(cls, "description", ""), "class": cls.__name__}
        for name, cls in _registry.items()
    ]
