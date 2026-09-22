from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import notifications

app = FastAPI(title="Personal Expense Tracker - Notification Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(notifications.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "notification-service"}