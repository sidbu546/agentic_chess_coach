"""Load openapi.yaml and validate JSON against any schema in components/schemas."""
from __future__ import annotations

import pathlib
from functools import lru_cache

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = pathlib.Path(__file__).resolve().parent.parent
URI = "urn:think64:openapi"

SPEC = yaml.safe_load((ROOT / "openapi.yaml").read_text())
REGISTRY = Registry().with_resource(URI, Resource.from_contents(SPEC, default_specification=DRAFT202012))


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    if name not in SPEC["components"]["schemas"]:
        raise KeyError(f"No schema named {name} in openapi.yaml")
    return Draft202012Validator({"$ref": f"{URI}#/components/schemas/{name}"}, registry=REGISTRY)


def errors(name: str, instance) -> list[str]:
    out = []
    for e in sorted(validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{where}: {e.message}"[:400])
    return out


# which schemas describe each endpoint: path -> (request, response)
ENDPOINTS = {
    ("GET", "/v1/health"): (None, "HealthResponse"),
    ("POST", "/v1/position"): ("PositionRequest", "PositionResponse"),
    ("POST", "/v1/move"): ("MoveRequest", "MoveResponse"),
    ("POST", "/v1/analyze"): ("AnalyzeRequest", "AnalyzeResponse"),
    ("POST", "/v1/compare"): ("CompareRequest", "CompareResponse"),
    ("POST", "/v1/verify"): ("VerifyRequest", "VerifyResponse"),
    ("POST", "/v1/game"): ("GameRequest", "GameResponse"),
}
