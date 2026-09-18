import os

# Unit/API tests must not require a running PostgreSQL server or psycopg driver.
# Production/integration tests override this with the real DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
