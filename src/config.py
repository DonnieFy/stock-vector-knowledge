"""配置加载模块"""

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG = {
    "embedding": {
        "model_name": "BAAI/bge-small-zh-v1.5",
        "device": "cpu",
    },
    "data": {
        "drafts_dir": "./data/drafts",
        "summaries_dir": "./data/summaries",
        "vectordb_dir": "./data/vectordb",
    },
    "collectors": {
        "enabled": ["ths", "tencent"],
        "request_interval": 1.0,
    },
}


class Config:
    """项目配置管理"""

    def __init__(self, config_path: str | None = None):
        self._data: dict[str, Any] = {}
        self._project_root = self._find_project_root()
        self._load(config_path)

    def _find_project_root(self) -> Path:
        """查找项目根目录（包含 pyproject.toml 的目录）"""
        current = Path(__file__).resolve().parent.parent
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                return current
            current = current.parent
        # 回退到 src 的上级目录
        return Path(__file__).resolve().parent.parent

    def _load(self, config_path: str | None):
        """加载配置文件"""
        if config_path:
            path = Path(config_path)
        else:
            path = self._project_root / "config.yaml"

        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = {}

        # 合并默认配置
        self._data = self._merge_defaults(DEFAULT_CONFIG, self._data)

    def _merge_defaults(self, defaults: dict, overrides: dict) -> dict:
        """递归合并默认配置和用户配置"""
        result = defaults.copy()
        for key, value in overrides.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(result[key], value)
            else:
                result[key] = value
        return result

    @property
    def project_root(self) -> Path:
        return self._project_root

    def get(self, key_path: str, default: Any = None) -> Any:
        """通过点分路径获取配置值，如 'embedding.model_name'"""
        keys = key_path.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def resolve_path(self, relative_path: str) -> Path:
        """将配置中的相对路径解析为绝对路径"""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return self._project_root / p

    @property
    def drafts_dir(self) -> Path:
        return self.resolve_path(self.get("data.drafts_dir", "./data/drafts"))

    @property
    def summaries_dir(self) -> Path:
        return self.resolve_path(self.get("data.summaries_dir", "./data/summaries"))

    @property
    def vectordb_dir(self) -> Path:
        return self.resolve_path(self.get("data.vectordb_dir", "./data/vectordb"))

    @property
    def embedding_model(self) -> str:
        return self.get("embedding.model_name", "BAAI/bge-small-zh-v1.5")

    @property
    def embedding_device(self) -> str:
        return self.get("embedding.device", "cpu")

    @property
    def enabled_collectors(self) -> list[str]:
        return self.get("collectors.enabled", ["ths", "tencent"])

    @property
    def request_interval(self) -> float:
        return self.get("collectors.request_interval", 1.0)

    @property
    def jiuyangongshe_phone(self) -> str:
        return self.get("jiuyangongshe.phone", "")
        
    @property
    def jiuyangongshe_password(self) -> str:
        return self.get("jiuyangongshe.password", "")

    @property
    def jiuyangongshe_token(self) -> str:
        return self.get("jiuyangongshe.token", "")

    @property
    def jiuyangongshe_timestamp(self) -> str:
        return self.get("jiuyangongshe.timestamp", "")

    @property
    def jiuyangongshe_cookies(self) -> str:
        return self.get("jiuyangongshe.cookies", "")

    @property
    def jiuyangongshe_data_dir(self) -> Path:
        return self.resolve_path("./data/jiuyangongshe")

    def update_jiuyangongshe_auth(self, token: str, timestamp: str, cookies: str):
        """更新韭研公社认证信息并保存到文件"""
        if "jiuyangongshe" not in self._data:
            self._data["jiuyangongshe"] = {}
            
        self._data["jiuyangongshe"]["token"] = token
        self._data["jiuyangongshe"]["timestamp"] = timestamp
        self._data["jiuyangongshe"]["cookies"] = cookies
        
        path = self._project_root / "config.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                import yaml
                data = yaml.safe_load(f) or {}
                
            if "jiuyangongshe" not in data:
                data["jiuyangongshe"] = {}
                
            data["jiuyangongshe"]["token"] = token
            data["jiuyangongshe"]["timestamp"] = timestamp
            data["jiuyangongshe"]["cookies"] = cookies
            
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)

# 全局单例
_config: Config | None = None


def get_config(config_path: str | None = None) -> Config:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


def reset_config():
    """重置配置（用于测试）"""
    global _config
    _config = None
