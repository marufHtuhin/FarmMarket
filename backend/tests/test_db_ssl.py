"""db_connect_args: TiDB Cloud TLS auto-detect + DB_SSL override.

No live TiDB connection is attempted anywhere here — there is no TiDB
account in this environment; the first Render deploy is the live test.
create_engine is lazy, so constructing an engine with the returned
connect_args proves the args are accepted without connecting.
"""
import os

import pytest
from sqlalchemy import create_engine

from app.config import database_pool_recycle, db_connect_args

TIDB_URL = ("mysql+pymysql://4aBcDeF.root:secret@"
            "gateway01.eu-central-1.prod.aws.tidbcloud.com:4000/farmmarket"
            "?charset=utf8mb4")
TIDB_URL_BARE = ("mysql://4aBcDeF.root:secret@"
                 "gateway01.us-west-2.prod.aws.tidbcloud.com:4000/farmmarket")
PLAIN_URL = "mysql+pymysql://root:pw@db.internal:3306/railway?charset=utf8mb4"
SQLITE_URL = "sqlite:///./farmmarket.db"


@pytest.fixture(autouse=True)
def _clean_tls_env(monkeypatch):
    monkeypatch.delenv("DB_SSL", raising=False)
    monkeypatch.delenv("DB_SSL_CA", raising=False)


def _ssl_ca(args):
    assert set(args) == {"ssl"}
    ca = args["ssl"]["ca"]
    assert isinstance(ca, str) and ca.endswith("cacert.pem")
    assert os.path.isfile(ca), f"CA bundle must exist on disk: {ca}"
    return ca


def test_tidb_host_auto_detects_verified_tls():
    _ssl_ca(db_connect_args(TIDB_URL))


def test_tidb_host_auto_detects_bare_mysql_scheme():
    # normalize_database_url rewrites mysql:// -> mysql+pymysql://, but the
    # helper must not depend on that having happened first.
    _ssl_ca(db_connect_args(TIDB_URL_BARE))


def test_plain_mysql_host_gets_no_tls():
    assert db_connect_args(PLAIN_URL) == {}


def test_non_mysql_scheme_gets_no_tls():
    assert db_connect_args("postgresql://u:p@h:5432/db") == {}


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "on"])
def test_db_ssl_truthy_forces_tls_on_any_host(monkeypatch, value):
    monkeypatch.setenv("DB_SSL", value)
    _ssl_ca(db_connect_args(PLAIN_URL))


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off"])
def test_db_ssl_falsy_overrides_tidb_auto_detect(monkeypatch, value):
    monkeypatch.setenv("DB_SSL", value)
    assert db_connect_args(TIDB_URL) == {}


def test_sqlite_gets_check_same_thread_only(monkeypatch):
    assert db_connect_args(SQLITE_URL) == {"check_same_thread": False}
    # TLS flags must never leak into SQLite connect args.
    monkeypatch.setenv("DB_SSL", "true")
    assert db_connect_args(SQLITE_URL) == {"check_same_thread": False}


def test_explicit_db_ssl_ca_path_still_honoured(monkeypatch):
    # The older opt-in path survives as the explicit-CA fallback: a user
    # who set DB_SSL_CA keeps their chosen bundle, even on a TiDB host.
    monkeypatch.setenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")
    args = db_connect_args(TIDB_URL)
    assert args == {"ssl_verify_cert": True, "ssl_verify_identity": True,
                    "ssl_ca": "/etc/ssl/certs/ca-certificates.crt"}


def test_default_url_reads_database_url_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TIDB_URL)
    _ssl_ca(db_connect_args())
    monkeypatch.setenv("DATABASE_URL", PLAIN_URL)
    assert db_connect_args() == {}


def test_args_usable_as_create_engine_connect_args():
    # create_engine is lazy: no connection is attempted (no live TiDB).
    engine = create_engine(TIDB_URL, connect_args=db_connect_args(TIDB_URL))
    assert engine.url.host.endswith(".tidbcloud.com")
    assert engine.url.port == 4000
    engine.dispose()
    sqlite_engine = create_engine(
        SQLITE_URL, connect_args=db_connect_args(SQLITE_URL))
    assert sqlite_engine.url.drivername == "sqlite"
    sqlite_engine.dispose()


def test_pool_recycle_follows_tls_decision(monkeypatch):
    assert database_pool_recycle(TIDB_URL) == 300
    assert database_pool_recycle(PLAIN_URL) is None
    monkeypatch.setenv("DB_SSL", "false")
    assert database_pool_recycle(TIDB_URL) is None
