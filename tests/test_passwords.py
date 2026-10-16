import pytest
from app.core.passwords import hash_password, verify_password

@pytest.mark.parametrize("password,hashed", [
    ("migration-test-🧪", "$bcrypt-sha256$2b,4$ct7FMcpKOeBqOXXJviXaYu$OoiBB3khst97jKIoHQvoassrqZMmSa."),
    ("migration-test-🧪", "$bcrypt-sha256$v=2,t=2b,r=4$LWAbD4AmSO2eoUOr3bBtFu$fC98ikYR3qDsxgrjqfYpGoOamlmHLty"),
    ("migration-test", "$2b$04$bedfViIuf6T.QegO6H8Hbe7XosIJ/H6N3fyGmohwAs24WFEBWp2VK"),
])
def test_legacy_password_migration(password, hashed):
    assert verify_password(password, hashed)
    assert not verify_password(password + "wrong", hashed)


def test_argon2id_long_unicode_password():
    password = "🧪" * 100
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password(password + "x", hashed)
