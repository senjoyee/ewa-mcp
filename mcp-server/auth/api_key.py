"""API Key authentication middleware."""

import os
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to validate API key in Authorization header."""
    
    def __init__(self, app):
        super().__init__(app)
        self.api_key = os.environ.get("API_KEY", "")
        self.header_name = os.environ.get("API_KEY_HEADER", "Authorization")
    
    async def dispatch(self, request: Request, call_next):
        """Validate API key on each request."""
        # Skip health check
        if request.url.path == "/health":
            return await call_next(request)
        
        # Skip if no API key configured (dev mode)
        if not self.api_key:
            return await call_next(request)
        
        # Get API key from header
        auth_header = request.headers.get(self.header_name, "")
        
        # Expected format: "Bearer <api_key>"
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]
        else:
            provided_key = auth_header
        
        # Validate
        if provided_key != self.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        return await call_next(request)
