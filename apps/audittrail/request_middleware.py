import uuid

from .events import reset_current_request, set_current_request


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_request_id = uuid.uuid4()
        token = set_current_request(request)
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = str(request.audit_request_id)
            return response
        finally:
            reset_current_request(token)
