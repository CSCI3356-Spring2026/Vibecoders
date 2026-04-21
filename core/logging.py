import contextvars
import json
import logging
import uuid

_request_id = contextvars.ContextVar("request_id", default="-")


def current_request_id():
    return _request_id.get()


class RequestIDMiddleware:
    header_name = "HTTP_X_REQUEST_ID"
    response_header = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (request.META.get(self.header_name) or "").strip() or uuid.uuid4().hex
        token = _request_id.set(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[self.response_header] = request_id
        return response


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = current_request_id()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
