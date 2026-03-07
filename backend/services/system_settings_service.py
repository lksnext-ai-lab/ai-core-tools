import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

import yaml
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.system_setting import SystemSetting
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemSettingsService:
    _defaults_cache: dict[str, dict[str, Any]] | None = None
    _defaults_lock = RLock()
    _defaults_path = Path(__file__).resolve().parents[1] / "system_defaults.yaml"

    def __init__(self, db: Session):
        self.db = db

    def load_defaults(self) -> dict[str, dict[str, Any]]:
        if self.__class__._defaults_cache is not None:
            return self.__class__._defaults_cache

        with self.__class__._defaults_lock:
            if self.__class__._defaults_cache is not None:
                return self.__class__._defaults_cache

            if not self.__class__._defaults_path.exists():
                raise RuntimeError(
                    f"System defaults file not found: {self.__class__._defaults_path}"
                )

            try:
                with self.__class__._defaults_path.open("r", encoding="utf-8") as file:
                    parsed = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                raise RuntimeError(
                    f"Malformed system defaults YAML: {self.__class__._defaults_path}"
                ) from exc

            if not isinstance(parsed, dict) or "settings" not in parsed:
                raise RuntimeError(
                    f"Malformed system defaults YAML: missing 'settings' map in {self.__class__._defaults_path}"
                )

            settings = parsed["settings"]
            if not isinstance(settings, dict):
                raise RuntimeError(
                    f"Malformed system defaults YAML: 'settings' must be a map in {self.__class__._defaults_path}"
                )

            self.__class__._defaults_cache = settings
            logger.info("System defaults loaded from %s", self.__class__._defaults_path)
            return settings

    def get_setting(self, key: str) -> Any:
        defaults = self.load_defaults()
        db_row = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()

        declared_type = self._get_declared_type(key=key, defaults=defaults, db_row=db_row)
        env_var_name = self._env_var_name(key)
        env_value = os.getenv(env_var_name)

        if env_value is not None:
            return self._cast_value(env_value, declared_type, key)

        if db_row is not None and db_row.value is not None:
            return self._cast_value(db_row.value, declared_type, key)

        default_meta = defaults.get(key)
        if default_meta and "value" in default_meta:
            return self._cast_value(default_meta.get("value"), declared_type, key)

        return None

    def get_all_settings(self) -> list[dict[str, Any]]:
        defaults = self.load_defaults()
        db_rows = self.db.query(SystemSetting).all()
        db_by_key = {row.key: row for row in db_rows}
        keys = sorted(set(defaults.keys()) | set(db_by_key.keys()))

        settings: list[dict[str, Any]] = []
        for key in keys:
            default_meta = defaults.get(key, {})
            db_row = db_by_key.get(key)

            declared_type = self._get_declared_type(key=key, defaults=defaults, db_row=db_row)
            category = (
                db_row.category
                if db_row and db_row.category
                else default_meta.get("category", "general")
            )
            description = (
                db_row.description
                if db_row and db_row.description
                else default_meta.get("description")
            )

            source, resolved_value = self._resolve_source_and_value(
                key=key,
                declared_type=declared_type,
                default_meta=default_meta,
                db_row=db_row,
            )

            settings.append(
                {
                    "key": key,
                    "value": db_row.value if db_row else None,
                    "type": declared_type,
                    "category": category,
                    "description": description,
                    "updated_at": db_row.updated_at if db_row else None,
                    "resolved_value": resolved_value,
                    "source": source,
                }
            )

        return settings

    def update_setting(self, key: str, value: str) -> SystemSetting:
        defaults = self.load_defaults()
        default_meta = defaults.get(key)
        if default_meta is None:
            raise KeyError(f"Unknown setting key: {key}")

        declared_type = str(default_meta.get("type", "string"))
        category = str(default_meta.get("category", "general"))
        description = default_meta.get("description")

        if value == "" and declared_type in {"integer", "float", "boolean"}:
            self.reset_setting(key)
            return SystemSetting(
                key=key,
                value=None,
                type=declared_type,
                category=category,
                description=description,
            )

        self._cast_value(value, declared_type, key)

        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting is None:
            setting = SystemSetting(key=key)
            self.db.add(setting)

        setting.value = value
        setting.type = declared_type
        setting.category = category
        setting.description = description

        try:
            self.db.commit()
            self.db.refresh(setting)
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return setting

    def reset_setting(self, key: str) -> None:
        defaults = self.load_defaults()
        if key not in defaults:
            raise KeyError(f"Unknown setting key: {key}")

        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting is None:
            return

        try:
            self.db.delete(setting)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def _resolve_source_and_value(
        self,
        key: str,
        declared_type: str,
        default_meta: dict[str, Any],
        db_row: SystemSetting | None,
    ) -> tuple[str, Any]:
        env_value = os.getenv(self._env_var_name(key))
        if env_value is not None:
            return "env", self._cast_value(env_value, declared_type, key)

        if db_row is not None and db_row.value is not None:
            return "db", self._cast_value(db_row.value, declared_type, key)

        if "value" in default_meta:
            return "default", self._cast_value(default_meta.get("value"), declared_type, key)

        if db_row is not None:
            return "db", None

        raise KeyError(f"Unknown setting key: {key}")

    def _get_declared_type(
        self,
        key: str,
        defaults: dict[str, dict[str, Any]],
        db_row: SystemSetting | None,
    ) -> str:
        if key in defaults:
            return str(defaults[key].get("type", "string"))
        if db_row is not None and db_row.type:
            return db_row.type
        raise KeyError(f"Unknown setting key: {key}")

    @staticmethod
    def _env_var_name(key: str) -> str:
        normalized = "".join(char if char.isalnum() else "_" for char in key).upper()
        return f"AICT_SYSTEM_{normalized}"

    @staticmethod
    def _cast_value(raw_value: Any, value_type: str, key: str) -> Any:
        casters = {
            "string": SystemSettingsService._cast_string,
            "integer": SystemSettingsService._cast_integer,
            "float": SystemSettingsService._cast_float,
            "boolean": SystemSettingsService._cast_boolean,
            "json": SystemSettingsService._cast_json,
            "string_list": SystemSettingsService._cast_string_list,
        }

        caster = casters.get(value_type)
        if caster is None:
            raise ValueError(f"Unsupported setting type '{value_type}'")

        try:
            return caster(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid value for setting '{key}' (type '{value_type}'): {raw_value}"
            ) from exc

    @staticmethod
    def _cast_string(raw_value: Any) -> str:
        return "" if raw_value is None else str(raw_value)

    @staticmethod
    def _cast_integer(raw_value: Any) -> int:
        return int(raw_value)

    @staticmethod
    def _cast_float(raw_value: Any) -> float:
        return float(raw_value)

    @staticmethod
    def _cast_boolean(raw_value: Any) -> bool:
        value_text = "" if raw_value is None else str(raw_value)
        return value_text.lower() in ("true", "1", "yes")

    @staticmethod
    def _cast_json(raw_value: Any) -> Any:
        if isinstance(raw_value, (dict, list, int, float, bool)) or raw_value is None:
            return raw_value
        return json.loads(str(raw_value))

    @staticmethod
    def _cast_string_list(raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        if raw_value is None:
            return []
        return [item.strip() for item in str(raw_value).split(",") if item.strip()]