"""Resolve schemas from their installed owner packages; never fetch from the network."""
from __future__ import annotations
import importlib
from typing import Mapping, Callable

SURVEY_URI = "https://openit.example/survey/v1/"


def external_schema(uri: str, sources: Mapping[str, Callable] | None = None) -> dict:
    if not uri.startswith(SURVEY_URI):
        raise ValueError("schema reference has no registered owner")
    name = uri[len(SURVEY_URI):].removesuffix(".json")
    if not name or "/" in name or "#" in name:
        raise ValueError("invalid external schema identifier")
    if sources and "survey" in sources:
        return {**sources["survey"](name), "$id": uri}
    # This owner is optional for consumers that do not exchange survey records.
    # A consumer of such a record must install the pinned owner schema package.
    try:
        owner = importlib.import_module("survey_schema")
    except ImportError as error:
        raise ValueError("openit-survey-schema is required to validate this contract") from error
    return {**owner.load_schema(name, version=1), "$id": uri}
