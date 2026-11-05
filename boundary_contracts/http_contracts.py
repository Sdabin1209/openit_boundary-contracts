"""Service-scoped OpenAPI contracts. JSON Schema records retain one definition.

No network lookup and no neighbouring working tree reads: external schema owners
are supplied by the application's wiring through their installed schema package.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import unquote, urljoin

import jsonschema

from .schemas_api import schema_dir, schema_registry, validator as record_validator

ROOT = Path(__file__).resolve().parent / "openapi"
SURVEY_URI = "https://openit.example/survey/v1/"
METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


class AuthorizationDenied(ValueError):
    """A declared role claim conflicts with the authenticated identity."""


class AuthenticationRequired(ValueError):
    """A declared authenticated actor is missing or untrusted."""


class ContractViolation(ValueError):
    """Only locations and rule names, never input values, are exposed."""


def catalog() -> dict:
    value = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    record_validator("HttpCatalog").validate(value)
    return value


def document(service: str) -> dict:
    entry = catalog()["services"][service]
    return json.loads((ROOT / entry["document"]).read_text(encoding="utf-8"))


def operations(service: str):
    for path, item in document(service)["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield method.upper(), path, operation


def _pointer(doc, fragment):
    for part in fragment.lstrip("/").split("/") if fragment else ():
        doc = doc[part.replace("~1", "/").replace("~0", "~")]
    return doc


class HttpContract:
    def __init__(self, service: str, *, schema_sources: Mapping[str, Callable[[str], dict]] | None = None, bindings: Mapping | None = None):
        self.service = service
        self.doc = document(service)
        record_validator("HttpServiceDocument").validate(self.doc)
        self.base = (ROOT / catalog()["services"][service]["document"]).as_uri()
        self._sources = dict(schema_sources or {})
        self._registry = schema_registry(schema_sources=self._sources)
        self._validators = {}
        self._bindings = dict(bindings or {})
        if bindings is not None:
            self.check(self.doc["x-bindings-schema"], self._bindings, "bindings")
        self._routes = []
        for method, path, op in operations(service):
            regex = "^" + re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", re.escape(path)) + "$"
            self._routes.append((method, path, re.compile(regex), op))

    def _external(self, uri):
        from .schema_sources import external_schema
        return external_schema(uri, self._sources)

    def validator(self, schema: dict):
        key = json.dumps(schema, sort_keys=True)
        if key not in self._validators:
            rooted = {"$id": self.base, **schema}
            jsonschema.Draft202012Validator.check_schema(rooted)
            self._validators[key] = jsonschema.Draft202012Validator(rooted, registry=self._registry,
                                                                    format_checker=jsonschema.FormatChecker())
        return self._validators[key]

    def check(self, schema: dict, value, where: str):
        errors = list(self.validator(schema).iter_errors(value))
        if errors:
            rules = sorted({str(e.validator) for e in errors})
            raise ContractViolation(where + " (" + schema.get("$ref", "inline").rsplit("/", 1)[-1] + "): " + ",".join(rules))

    def match(self, method: str, path: str):
        for m, template, pattern, op in self._routes:
            hit = pattern.fullmatch(path)
            if hit and m == method.upper():
                return template, op, {k: unquote(v) for k, v in hit.groupdict().items()}
        raise ContractViolation("undeclared operation")

    def operation(self, method: str, template: str):
        try:
            return self.doc["paths"][template][method.lower()]
        except KeyError:
            raise ContractViolation("undeclared operation") from None

    def bound(self, value):
        if isinstance(value, dict) and "binding" in value:
            try:
                return self._bindings[value["binding"]]
            except KeyError:
                raise ContractViolation("missing runtime binding") from None
        return value

    def verify_route(self, method, template, roles, max_body):
        op = self.operation(method, template)
        if set(roles) != set(self.bound(op["x-roles"])):
            raise ContractViolation("route roles differ from contract binding")
        if max_body != self.bound(op["x-max-body-bytes"]):
            raise ContractViolation("route body limit differs from contract binding")


    def request(self, method: str, template: str, *, params: Mapping, query: Mapping,
                headers: Mapping, body, raw: bytes = b"", streaming=False, role=None):
        op = self.operation(method, template)
        hs = {k.lower(): v for k, v in headers.items()}
        claim = op.get("x-role-claim")
        if claim and isinstance(body, dict):
            stated = body.get(claim["property"])
            actual = role.removeprefix(claim["prefix"]) if role else None
            if stated is not None and stated != actual:
                raise AuthorizationDenied("role claim conflicts with authenticated role")
        policy = op["x-user-policy"]
        required = self.bound(policy["required"])
        if "unless_roles" in policy and role in self.bound(policy["unless_roles"]):
            required = False
        if "when_roles" in policy and role not in self.bound(policy["when_roles"]):
            required = False
        user = hs.get("x-openit-user")
        trusted = "trusted_roles" not in policy or role in self.bound(policy["trusted_roles"])
        if required and (not user or not trusted):
            raise AuthenticationRequired("authenticated actor is required")
        if required and user:
            self.check({"$ref": "../schemas/HttpWire.schema.json#/$defs/User"}, user, "authenticated actor")
        self.check(op["x-query-schema"], dict(query), "query")
        for parameter in op.get("parameters", []):
            source = params if parameter["in"] == "path" else hs if parameter["in"] == "header" else query
            name = parameter["name"].lower() if parameter["in"] == "header" else parameter["name"]
            if name not in source:
                if parameter.get("required"):
                    raise ContractViolation(parameter["in"] + ": required")
            else:
                self.check(parameter["schema"], source[name], parameter["in"] + "." + name)
        rb = op.get("requestBody")
        if rb is None:
            if raw or body is not None or streaming:
                raise ContractViolation("body: absent")
            return
        media = rb["content"]
        # An omitted media type uses only the explicitly declared default.
        ct = hs.get("content-type", "").split(";", 1)[0].strip().lower()
        if ct and ct not in media:
            raise ContractViolation("content-type: enum")
        selected = ct or op["x-default-content-type"]
        if selected == "application/json":
            self.check(media[selected]["schema"], body, "body")
        elif not streaming and not isinstance(raw, bytes):
            raise ContractViolation("body: binary")

    def response(self, method: str, template: str, status: int, body, *, content_type: str | None = None,
                 headers: Mapping | None = None):
        op = self.operation(method, template)
        response = op["responses"].get(str(status))
        if response is None:
            raise ContractViolation("response.status: enum")
        media = response.get("content", {})
        if not media:
            if body is not None and body != b"":
                raise ContractViolation("response.body: absent")
            return
        ct = (content_type or ("application/json" if isinstance(body, (dict, list)) else "text/plain" if isinstance(body, str) else "application/octet-stream")).split(";", 1)[0].strip().lower()
        if ct not in media:
            raise ContractViolation("response.content-type: enum")
        schema = media[ct]["schema"]
        if ct == "application/json" or (ct.startswith("text/") and ct != "text/event-stream"):
            self.check(schema, body, "response.body")
        elif isinstance(body, (str, Mapping)) or not (isinstance(body, bytes) or hasattr(body, "__iter__")):
            raise ContractViolation("response.body: binary-stream")
        hs = {k.lower(): v for k, v in (headers or {}).items()}
        for name, rule in response.get("headers", {}).items():
            if name.lower() not in hs:
                if rule.get("required"):
                    raise ContractViolation("response.header: required")
            else:
                self.check(rule["schema"], hs[name.lower()], "response.header." + name)

    def lint(self):
        """Resolve every reference, including branches never reached by a sample."""
        seen = set()
        ids = set()

        def walk(node, base):
            if isinstance(node, list):
                for child in node:
                    walk(child, base)
            elif isinstance(node, dict):
                scope = urljoin(base, node.get("$id", ""))
                if "$ref" in node:
                    uri = urljoin(scope, node["$ref"])
                    if uri not in seen:
                        seen.add(uri)
                        resolved = self._registry.resolver(base_uri=scope).lookup(node["$ref"])
                        walk(resolved.contents, uri.split("#", 1)[0])
                for key, child in node.items():
                    if key != "$ref":
                        walk(child, scope)

        for template, methods in self.doc["paths"].items():
            for method, op in methods.items():
                if op["operationId"] in ids:
                    raise ContractViolation("duplicate operationId")
                ids.add(op["operationId"])
                expected = set(re.findall(r"\{([^}]+)\}", template))
                declared = [p["name"] for p in op.get("parameters", []) if p["in"] == "path"]
                if expected != set(declared) or len(declared) != len(set(declared)):
                    raise ContractViolation("path parameters do not match template")
                if "requestBody" in op and op["x-default-content-type"] not in op["requestBody"]["content"]:
                    raise ContractViolation("default media type is not declared")
                for response in op["responses"].values():
                    if "text/event-stream" in response.get("content", {}) and "x-event-schema" not in op:
                        raise ContractViolation("SSE event schema is missing")
                walk(op, self.base)
        return {"service": self.service, "operations": len(ids), "references": len(seen)}
