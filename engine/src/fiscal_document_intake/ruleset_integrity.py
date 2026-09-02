from __future__ import annotations

from pathlib import Path

from .core import ValidationError

TRUSTED_RULESET_SHA256 = {
    "cclass-trib-2026-06-22.json": "77c99d6fe94117628244fda08b9129cec8e3f813751faa4cab5686329fd6f7b3",
    "cfop-2026-08-25.json": "fa2b79d44a5cda07ea527b1f2b6a908dc7d6d830dfad5692b6161242da3b4a65",
    "revenue-cfop-rules-v1.json": "8d6af88b5a3fc71e4e148f191933536577b1e882ebd502f90dcf77012538087f",
    "ncm-2026-09-01.json": "e31877145fc597906b7570220c183450cf3085f8b1ca215e6eaa464ab08a6f00",
}


def verify_trusted_hash(path: Path, actual_hash: str, label: str) -> dict[str, str]:
    expected_hash = TRUSTED_RULESET_SHA256.get(path.name)
    if expected_hash is None:
        raise ValidationError(
            f"{label} não possui hash confiável registrado no plugin: {path.name}"
        )
    if actual_hash.casefold() != expected_hash:
        raise ValidationError(
            f"Hash do {label} diverge do valor confiável registrado: {path.name}"
        )
    return {
        "integrity_status": "VERIFIED",
        "expected_sha256": expected_hash,
    }
