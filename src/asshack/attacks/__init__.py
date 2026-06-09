from .base import Attack, AttackResult, NoAttack
from .prompt_injection import PromptInjection
from .metadata_attack import MetadataAttack
from .rug_pull import RugPull

REGISTRY = {
    "none": NoAttack,
    "prompt_injection": PromptInjection,
    "metadata_attack": MetadataAttack,
    "rug_pull": RugPull,
}

__all__ = [
    "Attack", "AttackResult", "NoAttack",
    "PromptInjection", "MetadataAttack", "RugPull", "REGISTRY",
]
