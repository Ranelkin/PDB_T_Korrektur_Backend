from starlette.middleware.base import BaseHTTPMiddleware
from log_config import setup_logging

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging("Request-logger")

class LogRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info("Raw request headers: %s", request.headers)
        body = await request.body()
        logger.info("Raw request body: %s", body)
        response = await call_next(request)
        return response
