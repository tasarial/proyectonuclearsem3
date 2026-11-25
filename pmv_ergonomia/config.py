import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "pmv-ergonomia-dev-key-change-in-production-2026")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("HTTPS", "0") == "1"
    
    # MySQL
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "pmv_ergonomia")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    
    # Login security
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_BASE_SECONDS = 30          # 30s after first block
    LOCKOUT_MAX_SECONDS = 600          # 10 minutes max
    LOCKOUT_MULTIPLIER = 2             # doubles each time

    # Cuenta Owner inicial (solo se usa si aún no existe ningún Owner)
    OWNER_USERNAME = os.getenv("OWNER_USERNAME", "owner")
    OWNER_PASSWORD = os.getenv("OWNER_PASSWORD", "")
    OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")

    # ---- IA de visión (opcional): sin clave, las fotos se marcan a mano
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5-5")

    # ---- Fotos
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024          # 8 MB por petición
    MAX_FOTO_BYTES = 6 * 1024 * 1024

    # ---- Agenda
    TIMEZONE = os.getenv("TIMEZONE", "America/Bogota")
    MIN_ANTICIPACION_HORAS = float(os.getenv("MIN_ANTICIPACION_HORAS", "2"))
