# DDL 急救站 JSON Schema

本 Schema 使用 JSON Schema Draft 2020-12。`tasks[].level` 的业务层级统一为 `minimum`（保底）、`advanced`（进阶）、`challenge`（挑战）。一条通知包含多个 DDL 时，所有任务聚合在 `tasks` 数组，每项任务使用 `ddl_id` 关联 `deadlines` 中的 DDL，并通过自己的 `deadline` 保存任务级截止时间；根级 `deadline` 保留最早截止时间以兼容旧调用方。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/ddl-rescue.schema.json",
  "title": "DDL 急救站作业计划",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "source", "deadline", "deliverables", "materials", "risks", "tasks", "plan", "status"
  ],
  "properties": {
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "title", "captured_at"],
      "properties": {
        "type": {"enum": ["text", "image", "pdf"]},
        "title": {"type": "string", "minLength": 1},
        "captured_at": {"type": "string", "format": "date-time"}
      }
    },
    "deadline": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": false,
          "required": ["raw", "normalized", "confidence", "source_span"],
          "properties": {
            "raw": {"type": "string", "minLength": 1},
            "normalized": {"type": "string", "format": "date-time"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "source_span": {"type": "string", "minLength": 1}
          }
        }
      ]
    },
    "deadlines": {
      "type": "array",
      "description": "一条通知中识别出的全部 DDL；根 deadline 为其中最早者。",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "title", "deadline"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "title": {"type": "string"},
          "deadline": {
            "type": "object",
            "additionalProperties": false,
            "required": ["raw", "normalized", "confidence", "source_span"],
            "properties": {
              "raw": {"type": "string", "minLength": 1},
              "normalized": {"type": "string", "format": "date-time"},
              "confidence": {"type": "number", "minimum": 0, "maximum": 1},
              "source_span": {"type": "string", "minLength": 1}
            }
          }
        }
      }
    },
    "deliverables": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "requirements"],
        "properties": {
          "name": {"type": "string", "minLength": 1},
          "requirements": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "materials": {"type": "array", "items": {"type": "string"}},
    "risks": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["type", "message", "severity"],
        "properties": {
          "type": {"enum": ["ambiguity", "conflict", "missing_material"]},
          "message": {"type": "string", "minLength": 1},
          "severity": {"enum": ["high", "medium", "low"]}
        }
      }
    },
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "title", "estimate_min", "dependency", "first_step", "level"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "title": {"type": "string", "minLength": 1},
          "estimate_min": {"type": "integer", "minimum": 0},
          "dependency": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": true
          },
          "first_step": {"type": "string", "minLength": 1},
          "level": {"enum": ["minimum", "advanced", "challenge"]},
          "ddl_id": {"type": "string", "minLength": 1},
          "deadline": {
            "type": "object",
            "additionalProperties": false,
            "required": ["raw", "normalized", "confidence", "source_span"],
            "properties": {
              "raw": {"type": "string", "minLength": 1},
              "normalized": {"type": "string", "format": "date-time"},
              "confidence": {"type": "number", "minimum": 0, "maximum": 1},
              "source_span": {"type": "string", "minLength": 1}
            }
          }
        }
      }
    },
    "plan": {
      "type": "object",
      "additionalProperties": false,
      "required": ["capacity_min", "required_min", "feasible", "days"],
      "properties": {
        "capacity_min": {"type": "integer", "minimum": 0},
        "required_min": {"type": "integer", "minimum": 0},
        "feasible": {"type": "boolean"},
        "days": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["date", "tasks"],
            "properties": {
              "date": {"type": "string", "format": "date"},
              "tasks": {"type": "array", "items": {"type": "string", "minLength": 1}}
            }
          }
        }
      }
    },
    "status": {"enum": ["draft", "confirmed", "in_progress", "done", "replanned"]}
  }
}
```

说明：JSON Schema 负责结构和取值范围校验；依赖是否有效、时间容量、层级闸门、排期合法性和冲突判断由确定性 Python 规则处理。
