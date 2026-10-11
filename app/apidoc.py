"""Мини-слой над Flask: валидация через Pydantic, авторизация по ролям и автогенерация OpenAPI 3.0.

Каждый эндпоинт объявляется декоратором `api.route(...)`; из него же строится /openapi.json,
поэтому документация не расходится с кодом (требование ТЗ: все методы описаны через OpenAPI).
"""
import re
from dataclasses import dataclass
from functools import wraps
from typing import Any, Optional, Type

from flask import Flask, Response, jsonify, request
from pydantic import BaseModel, ValidationError

from . import db as dbm
from .security import decode_token


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


@dataclass
class Ctx:
    user: Optional[dict] = None
    body: Optional[BaseModel] = None
    query: Optional[BaseModel] = None


_FIELD_RU = {"missing": "обязательное поле", "string_too_short": "слишком короткое значение",
             "string_too_long": "слишком длинное значение", "value_error": "некорректное значение"}


class Api:
    def __init__(self, app: Flask, title: str, version: str, description: str):
        self.app = app
        self.meta = {"title": title, "version": version, "description": description}
        self.ops: list[dict] = []
        self.tags: dict[str, str] = {}
        app.register_error_handler(ApiError, self._handle_api_error)
        app.register_error_handler(404, lambda e: (jsonify(error="not_found", message="Не найдено"), 404))
        app.register_error_handler(405, lambda e: (jsonify(error="method_not_allowed", message="Метод не поддерживается"), 405))
        app.register_error_handler(413, lambda e: (jsonify(error="too_large", message="Файл слишком большой"), 413))
        app.add_url_rule("/openapi.json", "openapi_json", lambda: jsonify(self.openapi()))
        app.add_url_rule("/docs", "swagger_ui", self._swagger_ui)

    # ------------------------------------------------------------------ ошибки
    @staticmethod
    def _handle_api_error(e: ApiError):
        payload = {"error": e.code, "message": e.message}
        if e.details is not None:
            payload["details"] = e.details
        return jsonify(payload), e.status

    # ------------------------------------------------------------------ роуты
    def route(self, rule: str, methods=("GET",), *, tag: str, summary: str, auth: Optional[tuple] = (),
              body: Optional[Type[BaseModel]] = None, query: Optional[Type[BaseModel]] = None,
              upload: bool = False, description: str = "", ok: str = "Успешно", status: int = 200,
              allow_unconfirmed: bool = False):
        """auth: None — публичный; () — любой авторизованный; ("candidate",) — только роль."""

        def deco(fn):
            endpoint = f"{fn.__module__}.{fn.__name__}"

            @wraps(fn)
            def view(**path_args):
                ctx = Ctx()
                if auth is not None:
                    ctx.user = self._authenticate(auth, allow_unconfirmed)
                if query is not None:
                    try:
                        ctx.query = query.model_validate(request.args.to_dict(flat=True))
                    except ValidationError as ve:
                        raise self._validation_error(ve)
                if body is not None:
                    raw = request.get_json(silent=True)
                    if raw is None:
                        raise ApiError(400, "bad_json", "Ожидалось тело запроса в формате JSON")
                    try:
                        ctx.body = body.model_validate(raw)
                    except ValidationError as ve:
                        raise self._validation_error(ve)
                result = fn(ctx, **path_args)
                if isinstance(result, Response):  # файлы (PDF) отдаются как есть
                    return result
                if isinstance(result, tuple):
                    data, code = result
                else:
                    data, code = result, status
                return jsonify(data), code

            self.app.add_url_rule(rule, endpoint, view, methods=list(methods))
            self.tags.setdefault(tag, tag)
            self.ops.append(dict(rule=rule, methods=[m.lower() for m in methods], tag=tag, summary=summary,
                                 auth=auth, body=body, query=query, upload=upload,
                                 description=description or (fn.__doc__ or "").strip(), ok=ok, status=status))
            return fn

        return deco

    # ------------------------------------------------------------------ авторизация
    def _authenticate(self, roles: tuple, allow_unconfirmed: bool) -> dict:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise ApiError(401, "unauthorized", "Требуется авторизация")
        claims = decode_token(header[7:])
        if not claims:
            raise ApiError(401, "invalid_token", "Токен недействителен или истёк")
        row = dbm.q1("SELECT * FROM users WHERE id = ?", (int(claims["sub"]),))
        if row is None:
            raise ApiError(401, "invalid_token", "Пользователь не найден")
        user = dict(row)
        if roles and user["role"] not in roles:
            raise ApiError(403, "forbidden", "Недостаточно прав для этого действия")
        if not user["email_confirmed"] and not allow_unconfirmed:
            raise ApiError(403, "email_not_confirmed", "Подтвердите адрес электронной почты")
        return user

    @staticmethod
    def _validation_error(ve: ValidationError) -> ApiError:
        items = []
        for err in ve.errors():
            loc = ".".join(str(p) for p in err["loc"])
            items.append({"field": loc, "message": err.get("msg", "") or _FIELD_RU.get(err["type"], "некорректное значение")})
        return ApiError(422, "validation_error", "Проверьте введённые данные", items)

    # ------------------------------------------------------------------ OpenAPI
    def openapi(self) -> dict:
        schemas: dict[str, Any] = {}

        def ref_of(model: Type[BaseModel]) -> dict:
            sch = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, sub in sch.pop("$defs", {}).items():
                schemas[name] = sub
            schemas[model.__name__] = sch
            return {"$ref": f"#/components/schemas/{model.__name__}"}

        paths: dict[str, dict] = {}
        for op in self.ops:
            path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", op["rule"])
            params = [{"name": n, "in": "path", "required": True,
                       "schema": {"type": "integer" if "int:" in op["rule"] else "string"}}
                      for n in re.findall(r"<(?:\w+:)?(\w+)>", op["rule"])]
            if op["query"] is not None:
                qs = op["query"].model_json_schema()
                req = set(qs.get("required", []))
                for pname, pschema in qs.get("properties", {}).items():
                    params.append({"name": pname, "in": "query", "required": pname in req,
                                   "schema": {k: v for k, v in pschema.items() if k != "title"}})
            spec: dict[str, Any] = {"tags": [op["tag"]], "summary": op["summary"],
                                    "description": op["description"], "parameters": params,
                                    "responses": {str(op["status"]): {"description": op["ok"]},
                                                  "400": {"description": "Некорректный запрос"},
                                                  "422": {"description": "Ошибка валидации (details — список полей)"}}}
            if op["auth"] is not None:
                spec["security"] = [{"bearerAuth": []}]
                spec["responses"]["401"] = {"description": "Нет или недействителен токен"}
                spec["responses"]["403"] = {"description": "Недостаточно прав / e-mail не подтверждён"}
                if op["auth"]:
                    spec["description"] = (spec["description"] + f"\n\nДоступно ролям: {', '.join(op['auth'])}.").strip()
            if "<" in op["rule"]:
                spec["responses"]["404"] = {"description": "Объект не найден"}
            if op["body"] is not None:
                spec["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref_of(op["body"])}}}
            if op["upload"]:
                spec["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": {
                    "type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}
            for m in op["methods"]:
                paths.setdefault(path, {})[m] = spec

        return {"openapi": "3.0.3",
                "info": {**self.meta},
                "tags": [{"name": t} for t in self.tags],
                "paths": paths,
                "components": {"schemas": schemas,
                               "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}}}

    @staticmethod
    def _swagger_ui():
        html = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>API — ФСП Карьера</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"></head>
<body><div id="ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>window.ui = SwaggerUIBundle({url: '/openapi.json', dom_id: '#ui', persistAuthorization: true});</script>
</body></html>"""
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
