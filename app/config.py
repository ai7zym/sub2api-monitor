"""应用配置：从 data/config.json 读取数据库连接等持久化配置。"""
import json
import os
import secrets

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_CONFIG_PATH = os.path.join(_DATA_DIR, "config.json")

# 抓取间隔（秒），默认 5 分钟
FETCH_INTERVAL_SECONDS = 300

# 单次 HTTP 请求超时（秒）
HTTP_TIMEOUT = 10

# 抓取并发数
FETCH_CONCURRENCY = 10

# ----------------------------- 邮件通知 -----------------------------
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587
SMTP_USER = "your_email@qq.com"
SMTP_PASSWORD = "your_smtp_password"
SMTP_FROM = "PriceMonitor <your_email@qq.com>"
SMTP_USE_TLS = True

ALERT_EMAIL_TO = ["your_alert_email@example.com"]

# ----------------------------- 持久化配置 -----------------------------
_config_cache: dict = {}
_jwt_secret_cache: str = ""


def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def load_config() -> dict:
    """加载 data/config.json，不存在返回空字典。"""
    global _config_cache, _jwt_secret_cache
    if _config_cache:
        return _config_cache
    _ensure_data_dir()
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
    else:
        _config_cache = {}
    _jwt_secret_cache = _config_cache.get("jwt_secret", "")
    return _config_cache


def save_config(data: dict) -> None:
    """保存配置到 data/config.json。"""
    global _config_cache
    _ensure_data_dir()
    _config_cache = data
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_initialized() -> bool:
    """检查是否已完成初始化设置。"""
    return load_config().get("initialized", False)


def get_database_url() -> str:
    """获取数据库连接串。未初始化时返回临时 SQLite（仅供 setup 过程使用）。"""
    cfg = load_config()
    return cfg.get("database_url",
                   f"sqlite:///{os.path.join(_DATA_DIR, 'price_monitor.db')}")


DATABASE_URL = get_database_url()  # 兼容旧代码的模块级引用


def get_jwt_secret() -> str:
    """JWT 签名密钥。首次运行时生成并持久化。"""
    global _jwt_secret_cache
    if _jwt_secret_cache:
        return _jwt_secret_cache
    cfg = load_config()
    secret = cfg.get("jwt_secret", "")
    if not secret:
        secret = secrets.token_hex(32)
        cfg["jwt_secret"] = secret
        save_config(cfg)
    _jwt_secret_cache = secret
    return secret
