import os
import math
from pathlib import Path
from .agent import ModelConfig


def load_env():
    path=Path(__file__).resolve().parents[1]/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1)
                os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))


def model_config():
    def price(key):
        try:
            value=float(os.environ.get(key,''));return value if value>=0 and math.isfinite(value) else None
        except ValueError:return None
    return ModelConfig(os.environ.get('AI_API_KEY',''),os.environ.get('AI_BASE_URL',''),os.environ.get('AI_MODEL',''),price('AI_INPUT_PRICE_PER_MILLION'),price('AI_OUTPUT_PRICE_PER_MILLION'),os.environ.get('AI_CURRENCY','CNY'))
