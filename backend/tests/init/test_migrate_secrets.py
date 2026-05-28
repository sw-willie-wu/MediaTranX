import pytest
from sqlmodel import Session, select
from app.db.models.api_connection import ApiConnection
from app.init.migrate_secrets import migrate_plaintext_keys


class _FakeCipher:
    scheme = "fake"
    def encrypt(self, p): return f"enc:fake:{p[::-1]}" if p else p
    def decrypt(self, t): return t

@pytest.fixture
def fake_cipher(monkeypatch):
    c = _FakeCipher()
    monkeypatch.setattr("app.init.migrate_secrets.get_secret_cipher", lambda: c)
    return c


def _seed(engine, **fields):
    with Session(engine) as s:
        c = ApiConnection(provider="openai", name="n", endpoint="http://x", **fields)
        s.add(c); s.commit(); s.refresh(c); return c.id

def _raw_key(engine, cid):
    with Session(engine) as s:
        return s.get(ApiConnection, cid).api_key


def test_encrypts_legacy_plaintext(real_db, fake_cipher):
    cid = _seed(real_db, api_key="sk-plain")
    migrate_plaintext_keys()
    assert _raw_key(real_db, cid) == "enc:fake:" + "sk-plain"[::-1]

def test_idempotent_skips_marked(real_db, fake_cipher):
    cid = _seed(real_db, api_key="enc:fake:already")
    migrate_plaintext_keys()
    assert _raw_key(real_db, cid) == "enc:fake:already"   # untouched

def test_skips_empty_keys(real_db, fake_cipher):
    cid = _seed(real_db, api_key=None)
    migrate_plaintext_keys()
    assert _raw_key(real_db, cid) is None

def test_foreign_scheme_left_untouched(real_db, fake_cipher):
    # a value that decrypt would reject is still only ENCRYPTED if unmarked;
    # marked foreign-scheme values are skipped (already have a marker)
    cid = _seed(real_db, api_key="enc:dpapi:foreign")
    migrate_plaintext_keys()
    assert _raw_key(real_db, cid) == "enc:dpapi:foreign"  # never overwritten


def test_multi_row_and_second_pass_is_noop(real_db, fake_cipher):
    plain1 = _seed(real_db, api_key="sk-one")
    plain2 = _seed(real_db, api_key="sk-two")
    marked = _seed(real_db, api_key="enc:fake:already")
    foreign = _seed(real_db, api_key="enc:dpapi:foreign")
    empty = _seed(real_db, api_key=None)

    migrate_plaintext_keys()
    after = {
        plain1: _raw_key(real_db, plain1),
        plain2: _raw_key(real_db, plain2),
        marked: _raw_key(real_db, marked),
        foreign: _raw_key(real_db, foreign),
        empty: _raw_key(real_db, empty),
    }
    assert after[plain1] == "enc:fake:" + "sk-one"[::-1]
    assert after[plain2] == "enc:fake:" + "sk-two"[::-1]
    assert after[marked] == "enc:fake:already"      # already marked -> untouched
    assert after[foreign] == "enc:dpapi:foreign"    # foreign scheme -> never overwritten
    assert after[empty] is None

    # Second pass: everything is now marked or empty -> pure no-op, no double-encryption
    migrate_plaintext_keys()
    assert _raw_key(real_db, plain1) == after[plain1]
    assert _raw_key(real_db, plain2) == after[plain2]
    assert _raw_key(real_db, marked) == after[marked]
    assert _raw_key(real_db, foreign) == after[foreign]
    assert _raw_key(real_db, empty) is None
