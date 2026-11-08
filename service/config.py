from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Model:
    alias: str
    model_id: str
    base_url: str
    api_key: str
    price_input_per_1m: float | None
    price_output_per_1m: float | None

    @property
    def priced(self) -> bool:
        return self.price_input_per_1m is not None and self.price_output_per_1m is not None


def load_model(alias: str) -> Model | None:
    prefix = alias.upper()
    base = os.getenv(f"{prefix}_LLM_BASE_URL", "").strip().rstrip("/")
    model_id = os.getenv(f"{prefix}_LLM_MODEL", "").strip()
    if not base or not model_id:
        return None
    if not (base.startswith("https://") or (os.getenv("ALLOW_HTTP_ENDPOINTS") == "1" and base.startswith("http://"))):
        raise ValueError(f"{prefix}_LLM_BASE_URL must use https (or explicitly allow http for local tests)")
    def price(name: str):
        val = os.getenv(f"{prefix}_{name}_USD_PER_1M")
        if val is None or not val.strip():
            return None
        p=float(val)
        if p < 0: raise ValueError("Token price cannot be negative")
        return p
    key_env=os.getenv(f"{prefix}_LLM_KEY_ENV", f"{prefix}_LLM_API_KEY")
    return Model(alias=alias, model_id=model_id, base_url=base,
                 api_key=os.getenv(key_env, ""),
                 price_input_per_1m=price("INPUT"),
                 price_output_per_1m=price("OUTPUT"))


def models() -> dict[str, Model]:
    return {m.alias:m for m in (load_model("fast"), load_model("strong")) if m}


def load_actions(path: str) -> dict:
    actions=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(actions,dict) or not actions.get("actions"):
        raise ValueError("Actions configuration requires a nonempty 'actions' array")
    out={}
    for action in actions["actions"]:
        aid=action.get("id")
        if not aid or aid in out: raise ValueError("Missing or duplicate action id")
        if action.get("kind") not in {"retrieve", "iterative"}:
            raise ValueError("Unsupported action kind")
        out[aid]=action
    return out


def load_calibration(path: str | None) -> dict:
    if not path: return {}
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(f"Calibration file not found: {p}")
    obj=json.loads(p.read_text(encoding="utf-8"))
    if obj.get("format_version")!=1:raise ValueError("Unknown calibration format")
    return obj
