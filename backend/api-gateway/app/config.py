import os

from dotenv import load_dotenv

load_dotenv()


SERVICE_URLS = {
    "users": os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001"),
    "expenses": os.getenv("EXPENSE_SERVICE_URL", "http://127.0.0.1:8002"),
    "categories": os.getenv("CATEGORY_SERVICE_URL", "http://127.0.0.1:8003"),
    "budgets": os.getenv("BUDGET_SERVICE_URL", "http://127.0.0.1:8004"),
    "reports": os.getenv("REPORT_SERVICE_URL", "http://127.0.0.1:8005"),
    "notifications": os.getenv("NOTIFICATION_SERVICE_URL", "http://127.0.0.1:8006"),
}
REQUEST_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT_SECONDS", "10"))