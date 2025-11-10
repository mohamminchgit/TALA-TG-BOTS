import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _load_env_file(env_path: Path) -> None:
    """Populate os.environ with key/value pairs from a .env file if present."""
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_BOOL_TRUE = {"1", "true", "t", "yes", "y", "on"}


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _BOOL_TRUE


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


@dataclass(frozen=True)
class TelegramCredentials:
    api_id: int
    api_hash: str


@dataclass(frozen=True)
class BotConfig:
    alias: str
    session_path: Path
    group_id: str
    phone_number: Optional[str]
    phone_password: Optional[str]
    ack_messages: bool
    confirmation_timeout_seconds: int
    cancel_ack_delay_seconds: int


@dataclass(frozen=True)
class RedisConfig:
    url: str
    group_events_channel: str = "group_events"
    execution_commands_channel: str = "execution_commands"
    execution_results_channel: str = "execution_results"
    admin_commands_channel: str = "admin_commands"
    admin_reports_channel: str = "admin_reports"


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class EngineConfig:
    reconciliation_interval_seconds: int
    stale_order_seconds: int
    minimum_profit_spread: int
    executed_trades_cache_key: str
    executed_trades_cache_ttl_seconds: int
    predictive_price_delta: int
    predictive_suffix_digits: int
    speculative_trade_timeout_seconds: int
    exit_break_even_timeout_seconds: int
    exit_stop_loss_timeout_seconds: int
    stop_loss_price_offset: int
    circuit_breaker_pause_seconds: int
    fixed_spread_delta: int
    base_carry_limit: int
    opportunity_carry_limit: int
    source_order_expiry_seconds: int


@dataclass(frozen=True)
class Settings:
    telegram: TelegramCredentials
    source_bot: BotConfig
    destination_bot: BotConfig
    redis: RedisConfig
    database: DatabaseConfig
    log_level: str
    engine: EngineConfig
    admin_bot: "AdminBotConfig"


@dataclass(frozen=True)
class AdminBotConfig:
    enabled: bool
    bot_token: Optional[str]
    chat_id: Optional[int]
    status_refresh_seconds: int


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def get_settings(env_path: Optional[Path] = None) -> Settings:
    """Return cached application settings loaded from environment variables."""
    if env_path is None:
        env_path = Path(".env")
    _load_env_file(env_path)

    telegram = TelegramCredentials(
        api_id=int(_require_env("TELEGRAM_API_ID")),
        api_hash=_require_env("TELEGRAM_API_HASH"),
    )

    database_path = Path(os.getenv("DATABASE_PATH", "data/database.db")).resolve()
    _ensure_parent(database_path)

    auto_n_delay_seconds = max(0, _int_env("AUTO_N_DELAY_SECONDS", 3))

    def build_bot(prefix: str) -> BotConfig:
        alias = _require_env(f"{prefix}_ALIAS")
        session_path = Path(os.getenv(f"{prefix}_SESSION_FILE", f"sessions/{prefix.lower()}_bot.session")).resolve()
        _ensure_parent(session_path)
        group_id = _require_env(f"{prefix}_GROUP")
        phone_number = os.getenv(f"{prefix}_PHONE_NUMBER")
        phone_password = os.getenv(f"{prefix}_PHONE_PASSWORD")
        ack_messages = _as_bool(os.getenv(f"{prefix}_ACK_MESSAGES", "false"))
        confirmation_timeout_seconds = int(os.getenv(f"{prefix}_CONFIRMATION_TIMEOUT_SECONDS", "15"))
        return BotConfig(
            alias=alias,
            session_path=session_path,
            group_id=group_id,
            phone_number=phone_number,
            phone_password=phone_password,
            ack_messages=ack_messages,
            confirmation_timeout_seconds=confirmation_timeout_seconds,
            cancel_ack_delay_seconds=auto_n_delay_seconds,
        )

    redis = RedisConfig(
        url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    predictive_price_delta = max(0, _int_env("PREDICTIVE_PRICE_DELTA", _int_env("PREDICTIVE_SPREAD", 10)))
    predictive_suffix_digits = max(1, _int_env("PREDICTIVE_SUFFIX_DIGITS", 4))
    fixed_spread_delta = max(0, _int_env("FIXED_SPREAD_DELTA", predictive_price_delta or 10))
    base_carry_limit = max(1, _int_env("BASE_CARRY_LIMIT", 1))
    opportunity_raw = _int_env("OPPORTUNITY_CARRY_LIMIT", 3)
    if opportunity_raw < 0:
        opportunity_carry_limit = base_carry_limit
    elif opportunity_raw == 0:
        opportunity_carry_limit = 0
    else:
        opportunity_carry_limit = opportunity_raw if opportunity_raw >= base_carry_limit else base_carry_limit

    engine = EngineConfig(
        reconciliation_interval_seconds=max(1, _int_env("ENGINE_RECONCILIATION_INTERVAL_SECONDS", 60)),
        stale_order_seconds=max(0, _int_env("ENGINE_STALE_ORDER_SECONDS", 900)),
        minimum_profit_spread=max(0, _int_env("MINIMUM_PROFIT_SPREAD", 10)),
        executed_trades_cache_key=os.getenv("EXECUTED_TRADES_CACHE_KEY", "executed_trades_cache"),
        executed_trades_cache_ttl_seconds=max(0, _int_env("EXECUTED_CACHE_EXPIRATION_SECONDS", 3600)),
        predictive_price_delta=predictive_price_delta,
        predictive_suffix_digits=predictive_suffix_digits,
        speculative_trade_timeout_seconds=max(1, _int_env("SPECULATIVE_TRADE_TIMEOUT_SECONDS", 60)),
        exit_break_even_timeout_seconds=max(1, _int_env("EXIT_STRATEGY_TIMEOUT_SECONDS", 2)),
        exit_stop_loss_timeout_seconds=max(1, _int_env("EMERGENCY_TIMEOUT_SECONDS", 4)),
        stop_loss_price_offset=max(1, _int_env("STOP_LOSS_PRICE_OFFSET", 5)),
        circuit_breaker_pause_seconds=max(0, _int_env("CIRCUIT_BREAKER_DURATION_MINUTES", 10)) * 60,
        fixed_spread_delta=fixed_spread_delta,
        base_carry_limit=base_carry_limit,
        opportunity_carry_limit=opportunity_carry_limit,
        source_order_expiry_seconds=max(1, _int_env("SOURCE_ORDER_EXPIRY_SECONDS", 60)),
    )

    admin_bot_token = os.getenv("ADMIN_BOT_TOKEN")
    admin_bot_chat_id_raw = os.getenv("ADMIN_BOT_CHAT_ID")
    admin_bot_enabled = bool(admin_bot_token and admin_bot_chat_id_raw)
    admin_chat_id = None
    if admin_bot_chat_id_raw:
        try:
            admin_chat_id = int(admin_bot_chat_id_raw)
        except ValueError:
            raise RuntimeError(f"Invalid ADMIN_BOT_CHAT_ID value: {admin_bot_chat_id_raw}")
    status_refresh_seconds = max(5, _int_env("ADMIN_STATUS_REFRESH_SECONDS", 30))
    admin_bot = AdminBotConfig(
        enabled=admin_bot_enabled,
        bot_token=admin_bot_token,
        chat_id=admin_chat_id,
        status_refresh_seconds=status_refresh_seconds,
    )

    source_bot_config = build_bot("SOURCE")
    destination_bot_config = build_bot("DESTINATION")

    if source_bot_config.session_path.resolve() == destination_bot_config.session_path.resolve():
        raise RuntimeError(
            "SOURCE_SESSION_FILE and DESTINATION_SESSION_FILE resolve to the same path. "
            "Configure distinct session files for each agent to avoid Telethon SQLite locks."
        )

    return Settings(
        telegram=telegram,
        source_bot=source_bot_config,
        destination_bot=destination_bot_config,
        redis=redis,
        database=DatabaseConfig(path=database_path),
        log_level=log_level,
        engine=engine,
        admin_bot=admin_bot,
    )
