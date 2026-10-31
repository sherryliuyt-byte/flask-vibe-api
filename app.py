from datetime import datetime, timezone

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


app = Flask(__name__)
app.json.ensure_ascii = False

tasks = [
    {
        "id": 1,
        "title": "範例任務",
        "description": "這是一筆記憶體中的模擬任務。",
    }
]


def json_response(status, message, data, http_status):
    return jsonify(
        {
            "status": status,
            "message": message,
            "data": data,
        }
    ), http_status


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    http_status = error.code or 500
    message = {
        400: "請求格式錯誤。",
        404: "找不到指定資源。",
        405: "不支援此 HTTP 方法。",
    }.get(http_status, error.description)

    return json_response("error", message, None, http_status)


@app.get("/api/health")
def health_check():
    return json_response(
        "success",
        "服務運作中。",
        {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        200,
    )


@app.get("/api/tasks")
def get_tasks():
    return json_response("success", "取得任務清單成功。", tasks, 200)


@app.post("/api/tasks")
def create_task():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_response("error", "請提供合法的 JSON 物件。", None, 400)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return json_response("error", "必填欄位 title 不可為空。", None, 400)

    description = payload.get("description", "")
    if not isinstance(description, str):
        return json_response("error", "欄位 description 必須是字串。", None, 400)

    task = {
        "id": max((item["id"] for item in tasks), default=0) + 1,
        "title": title.strip(),
        "description": description,
    }
    tasks.append(task)

    return json_response("success", "新增任務成功。", task, 201)


@app.get("/api/tasks/<int:task_id>")
def get_task(task_id):
    task = next((item for item in tasks if item["id"] == task_id), None)

    if task is None:
        return json_response("error", "找不到指定任務。", None, 404)

    return json_response("success", "取得任務成功。", task, 200)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)