"""Генерация OpenAPI 3.0 контракта M43."""
from django.conf import settings


def platform_version() -> str:
    return getattr(settings, "DELAYU_PLATFORM_VERSION", "2.2.0")


def build_openapi_spec() -> dict:
    version = platform_version()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "ДелаЮ REST API",
            "version": version,
            "description": "Платформа управления делами ЮГИт. Аутентификация: сессия Django или API-ключ (Bearer).",
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Bearer dlyu_… (ключ из раздела Интеграции → API)",
                },
                "SessionAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                },
            },
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["ok", "degraded"]},
                        "platform": {"type": "string"},
                        "version": {"type": "string"},
                        "checks": {"type": "object"},
                    },
                },
                "SearchHit": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "type_label": {"type": "string"},
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "score": {"type": "number"},
                    },
                },
                "AiPolicy": {
                    "type": "object",
                    "properties": {
                        "model_name": {"type": "string"},
                        "max_requests_per_day": {"type": "integer"},
                        "allow_pii": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                },
                "IntegrationMessage": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "endpoint": {"type": "string"},
                        "direction": {"type": "string"},
                        "status": {"type": "string"},
                        "retry_count": {"type": "integer"},
                        "error_text": {"type": "string"},
                        "external_id": {"type": "string"},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "MailDeliveryLog": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "direction": {"type": "string"},
                        "recipient": {"type": "string"},
                        "subject": {"type": "string"},
                        "event_code": {"type": "string"},
                        "success": {"type": "boolean"},
                        "error_message": {"type": "string"},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
            },
        },
        "paths": {
            "/api/v1/health/": {
                "get": {
                    "summary": "Проверка доступности",
                    "tags": ["Система"],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/openapi.json": {
                "get": {
                    "summary": "OpenAPI спецификация",
                    "tags": ["Система"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {"200": {"description": "JSON OpenAPI 3.0"}},
                }
            },
            "/api/v1/cases/": {
                "get": {
                    "summary": "Реестр дел (M22)",
                    "tags": ["Дела"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {"200": {"description": "Список дел"}},
                }
            },
            "/api/v1/tasks/": {
                "get": {
                    "summary": "Задачи текущего пользователя",
                    "tags": ["Задачи"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {"200": {"description": "Список задач"}},
                }
            },
            "/api/v1/modules/": {
                "get": {
                    "summary": "Каталог модулей",
                    "tags": ["Система"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {"200": {"description": "Модули платформы"}},
                }
            },
            "/api/v1/search/": {
                "get": {
                    "summary": "Глобальный поиск (M33)",
                    "tags": ["Поиск"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "minLength": 2},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Результаты",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "results": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/SearchHit"},
                                            }
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/calendar/events/": {
                "get": {
                    "summary": "События календаря / задачи",
                    "tags": ["Календарь"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {"200": {"description": "FullCalendar JSON"}},
                }
            },
            "/api/v1/integration/messages/": {
                "get": {
                    "summary": "Очередь интеграционных сообщений (M42)",
                    "tags": ["Интеграции"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {"name": "status", "in": "query", "schema": {"type": "string"}},
                        {"name": "endpoint", "in": "query", "schema": {"type": "string"}},
                        {"name": "direction", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "Список сообщений и метрики очереди",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "results": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/IntegrationMessage"},
                                            },
                                            "count": {"type": "integer"},
                                            "metrics": {"type": "object"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/integration/messages/{id}/retry/": {
                "post": {
                    "summary": "Повторная отправка сообщения",
                    "tags": ["Интеграции"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {"200": {"description": "Сообщение поставлено в очередь"}},
                }
            },
            "/api/v1/integration/messages/{id}/dead-letter/": {
                "post": {
                    "summary": "Перевод в dead letter",
                    "tags": ["Интеграции"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {"200": {"description": "Статус dead_letter"}},
                }
            },
            "/api/v1/integration/queue/process/": {
                "post": {
                    "summary": "Обработка pending-очереди",
                    "tags": ["Интеграции"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}},
                    ],
                    "responses": {"200": {"description": "Статистика обработки"}},
                }
            },
            "/api/v1/notifications/delivery/": {
                "get": {
                    "summary": "Журнал доставки уведомлений (M78)",
                    "tags": ["Уведомления"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "parameters": [
                        {"name": "success", "in": "query", "schema": {"type": "string"}},
                        {"name": "direction", "in": "query", "schema": {"type": "string"}},
                        {"name": "event_code", "in": "query", "schema": {"type": "string"}},
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "Логи SMTP/push",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "results": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/MailDeliveryLog"},
                                            },
                                            "count": {"type": "integer"},
                                            "metrics": {"type": "object"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/ai/policy/": {
                "get": {
                    "summary": "Политика ИИ подсистемы (M66)",
                    "tags": ["ИИ"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Текущая политика",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AiPolicy"}
                                }
                            },
                        }
                    },
                },
                "patch": {
                    "summary": "Обновление политики ИИ",
                    "tags": ["ИИ"],
                    "security": [{"ApiKeyAuth": []}, {"SessionAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AiPolicy"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Обновлённая политика",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AiPolicy"}
                                }
                            },
                        }
                    },
                },
            },
            "/api/v1/dadata/suggest/": {
                "post": {
                    "summary": "Подсказки DaData (сессия)",
                    "tags": ["Интеграции"],
                    "security": [{"SessionAuth": []}],
                    "responses": {"200": {"description": "suggestions[]"}},
                }
            },
            "/api/v1/integration/inbound/{subsystem}/{endpoint}/": {
                "post": {
                    "summary": "Входящий webhook (ЕПГУ, 1С…)",
                    "tags": ["Интеграции"],
                    "parameters": [
                        {"name": "subsystem", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "endpoint", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Результат обработчика"}},
                }
            },
            "/api/v1/telegram/{subsystem}/": {
                "post": {
                    "summary": "Webhook Telegram Bot",
                    "tags": ["Интеграции"],
                    "parameters": [
                        {"name": "subsystem", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }


def openapi_spec():
    return build_openapi_spec()
