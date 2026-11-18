"""DATABASE_URL normalization (PaaS MySQL addons hand out bare mysql:// URLs)."""
import os

from app.config import (
    database_pool_recycle,
    database_ssl_args,
    normalize_database_url,
)


def test_bare_mysql_url_gets_pymysql_and_charset():
    out = normalize_database_url("mysql://root:pw@db.internal:3306/railway")
    assert out == "mysql+pymysql://root:pw@db.internal:3306/railway?charset=utf8mb4"


def test_existing_pymysql_url_keeps_scheme_adds_charset():
    out = normalize_database_url(
        "mysql+pymysql://root:pw@127.0.0.1:3307/farmmarket_db")
    assert out == ("mysql+pymysql://root:pw@127.0.0.1:3307/farmmarket_db"
                   "?charset=utf8mb4")


def test_existing_charset_is_kept():
    out = normalize_database_url("mysql://root:pw@h:3306/db?charset=utf8mb4")
    assert out == "mysql+pymysql://root:pw@h:3306/db?charset=utf8mb4"


def test_sqlite_passes_through():
    assert normalize_database_url("sqlite:///./farmmarket.db") == \
        "sqlite:///./farmmarket.db"


def test_whitespace_is_stripped():
    out = normalize_database_url("  mysql://root:pw@h:3306/db  ")
    assert out.startswith("mysql+pymysql://")


def test_other_schemes_pass_through():
    assert normalize_database_url("postgresql://u:p@h:5432/db") == \
        "postgresql://u:p@h:5432/db"


# --- TLS connect args (TiDB Cloud Starter) ---

def test_no_ssl_by_default():
    os.environ.pop("DB_SSL_CA", None)
    assert database_ssl_args("mysql://root:pw@h:3306/db") == {}
    assert database_pool_recycle("mysql://root:pw@h:3306/db") is None


def test_ssl_ca_env_enables_verified_tls(monkeypatch):
    monkeypatch.setenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")
    args = database_ssl_args("mysql://root:pw@h:3306/db")
    assert args == {"ssl_verify_cert": True, "ssl_verify_identity": True,
                    "ssl_ca": "/etc/ssl/certs/ca-certificates.crt"}
    assert database_pool_recycle("mysql://root:pw@h:3306/db") == 300


def test_ssl_flags_in_url_enable_tls(monkeypatch):
    monkeypatch.delenv("DB_SSL_CA", raising=False)
    args = database_ssl_args(
        "mysql://root:pw@h:4000/db?ssl_verify_cert=true")
    assert args["ssl_verify_cert"] is True
    assert args["ssl_verify_identity"] is True


def test_ssl_never_applies_to_sqlite(monkeypatch):
    monkeypatch.setenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")
    assert database_ssl_args("sqlite:///./farmmarket.db") == {}
    assert database_pool_recycle("sqlite:///./farmmarket.db") is None
