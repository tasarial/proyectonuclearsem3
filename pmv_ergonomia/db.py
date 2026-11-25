import pymysql
from pymysql.cursors import DictCursor
from config import Config
from contextlib import contextmanager

def get_connection():
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        port=Config.MYSQL_PORT,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False
    )

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql, args=None, one=False):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            if one:
                return cur.fetchone()
            return cur.fetchall()

def execute(sql, args=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.lastrowid
