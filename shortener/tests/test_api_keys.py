"""
API Key（Personal Access Token）測試

涵蓋：
- 金鑰生成與雜湊工具（shortener/auth.py）
- API Key Bearer 認證（成功 / 無效 / 撤銷 / 停用帳號，JWT 不受影響）
- 網頁管理頁（建立與一次性顯示、上限、撤銷、權限）
"""

import pytest
from django.urls import reverse
from ninja.testing import TestClient

from shortener.auth import API_KEY_PREFIX, generate_api_key, hash_api_key
from shortener.models import ApiKey

from ninja_shortener.api import api


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def make_api_key(db):
    """建立指定用戶的 API Key，回傳 (ApiKey 實例, 金鑰明文)"""

    def _make(user, name='test key'):
        raw_key = generate_api_key()
        obj = ApiKey.objects.create(
            owner=user,
            name=name,
            key_hash=hash_api_key(raw_key),
            prefix=raw_key[:8],
        )
        return obj, raw_key

    return _make


@pytest.fixture
def api_client_with_token():
    """以指定 Bearer token 建立 Ninja TestClient"""

    def _make(token):
        return TestClient(api, headers={'Authorization': f'Bearer {token}'})

    return _make


# =============================================================================
# 金鑰生成與雜湊工具
# =============================================================================


def test_generate_api_key_format():
    """金鑰以 sk_ 開頭、長度足夠、每次生成皆不同"""
    key1 = generate_api_key()
    key2 = generate_api_key()

    assert key1.startswith(API_KEY_PREFIX)
    assert len(key1) == 46  # sk_ + token_urlsafe(32) 的 43 字元
    assert key1 != key2


def test_hash_api_key_deterministic():
    """同一金鑰雜湊結果固定，且為 64 字元十六進位（SHA-256）"""
    key = generate_api_key()

    assert hash_api_key(key) == hash_api_key(key)
    assert len(hash_api_key(key)) == 64
    assert hash_api_key(key) != hash_api_key(generate_api_key())


# =============================================================================
# API Key 認證
# =============================================================================


@pytest.mark.django_db
def test_api_key_can_create_link(test_user, make_api_key, api_client_with_token):
    """持有效 API Key 可建立短網址，owner 正確歸屬"""
    _, raw_key = make_api_key(test_user)
    client = api_client_with_token(raw_key)

    response = client.post('/shorten', json={'original_url': 'https://example.com/'})

    assert response.status_code == 200
    assert response.json()['owner'] == test_user.id


@pytest.mark.django_db
def test_invalid_api_key_rejected(api_client_with_token):
    """不存在的 API Key 回 401"""
    client = api_client_with_token(generate_api_key())  # 未入庫的金鑰

    response = client.post('/shorten', json={'original_url': 'https://example.com/'})

    assert response.status_code == 401


@pytest.mark.django_db
def test_revoked_api_key_rejected(test_user, make_api_key, api_client_with_token):
    """已撤銷（刪除）的 API Key 回 401"""
    api_key, raw_key = make_api_key(test_user)
    api_key.delete()
    client = api_client_with_token(raw_key)

    response = client.post('/shorten', json={'original_url': 'https://example.com/'})

    assert response.status_code == 401


@pytest.mark.django_db
def test_inactive_user_api_key_rejected(test_user, make_api_key, api_client_with_token):
    """帳號停用後其 API Key 一併失效"""
    _, raw_key = make_api_key(test_user)
    test_user.is_active = False
    test_user.save()
    client = api_client_with_token(raw_key)

    response = client.post('/shorten', json={'original_url': 'https://example.com/'})

    assert response.status_code == 401


@pytest.mark.django_db
def test_api_key_updates_last_used_at(test_user, make_api_key, api_client_with_token):
    """成功認證後更新 last_used_at"""
    api_key, raw_key = make_api_key(test_user)
    assert api_key.last_used_at is None

    client = api_client_with_token(raw_key)
    client.post('/shorten', json={'original_url': 'https://example.com/'})

    api_key.refresh_from_db()
    assert api_key.last_used_at is not None


@pytest.mark.django_db
def test_jwt_auth_still_works(ninja_authenticated_client):
    """換用 ApiKeyOrJWTAuth 後，既有 JWT 認證行為不變"""
    response = ninja_authenticated_client.post(
        '/shorten', json={'original_url': 'https://example.com/'}
    )

    assert response.status_code == 200


# =============================================================================
# 網頁管理頁
# =============================================================================


@pytest.mark.django_db
def test_api_keys_page_requires_login(client):
    """未登入訪問管理頁會被導向登入頁"""
    response = client.get(reverse('api_keys'))

    assert response.status_code == 302
    assert reverse('login') in response.url


def _extract_plaintext_keys(content: str) -> list[str]:
    """從頁面內容抽出看起來像完整金鑰明文的片段（sk_ 開頭且夠長）

    模板的使用範例含 `sk_...` 字樣，以長度門檻排除。
    """
    cleaned = content
    for ch in ('>', '<', "'", '"'):
        cleaned = cleaned.replace(ch, ' ')
    return [t for t in cleaned.split() if t.startswith('sk_') and len(t) >= 40]


@pytest.mark.django_db
def test_create_api_key_shows_plaintext_once(authenticated_client, authenticated_user):
    """建立後明文只顯示一次（可對回 key_hash），之後頁面僅剩 prefix"""
    response = authenticated_client.post(
        reverse('create_api_key'), {'name': 'Chrome 擴充套件'}, follow=True
    )

    api_key = ApiKey.objects.get(owner=authenticated_user)
    assert [str(m) for m in response.context['messages']] == [
        'API Key 已建立，請立即複製保存——它只會顯示這一次'
    ]
    plaintexts = set(_extract_plaintext_keys(response.content.decode()))
    assert len(plaintexts) == 1
    assert hash_api_key(plaintexts.pop()) == api_key.key_hash

    # 再次載入頁面：明文不再出現，只剩 prefix
    content2 = authenticated_client.get(reverse('api_keys')).content.decode()
    assert api_key.prefix in content2
    assert _extract_plaintext_keys(content2) == []


@pytest.mark.django_db
def test_create_api_key_respects_limit(authenticated_client, authenticated_user, settings):
    """達到 USER_MAX_API_KEYS 上限後拒絕再建立"""
    settings.USER_MAX_API_KEYS = 2
    for i in range(2):
        authenticated_client.post(reverse('create_api_key'), {'name': f'key-{i}'})

    response = authenticated_client.post(
        reverse('create_api_key'), {'name': 'key-overflow'}, follow=True
    )

    assert ApiKey.objects.filter(owner=authenticated_user).count() == 2
    assert '上限' in response.content.decode()


@pytest.mark.django_db
def test_delete_api_key(authenticated_client, authenticated_user, make_api_key):
    """擁有者可撤銷自己的金鑰"""
    api_key, _ = make_api_key(authenticated_user)

    response = authenticated_client.post(reverse('delete_api_key', args=[api_key.id]))

    assert response.status_code == 302
    assert not ApiKey.objects.filter(pk=api_key.pk).exists()


@pytest.mark.django_db
def test_cannot_delete_other_users_api_key(authenticated_client, other_user, make_api_key):
    """無法撤銷他人的金鑰（404，金鑰仍存在）"""
    api_key, _ = make_api_key(other_user)

    response = authenticated_client.post(reverse('delete_api_key', args=[api_key.id]))

    assert response.status_code == 404
    assert ApiKey.objects.filter(pk=api_key.pk).exists()


@pytest.mark.django_db
def test_create_api_key_get_does_not_create(authenticated_client, authenticated_user):
    """GET 建立端點只會導回管理頁，不會建立金鑰"""
    response = authenticated_client.get(reverse('create_api_key'))

    assert response.status_code == 302
    assert response.url == reverse('api_keys')
    assert not ApiKey.objects.filter(owner=authenticated_user).exists()


@pytest.mark.django_db
def test_create_api_key_name_default_and_truncation(authenticated_client, authenticated_user):
    """名稱空白時預設為「未命名」、過長截斷至 100 字元；prefix 為明文前 8 字元"""
    authenticated_client.post(reverse('create_api_key'), {'name': '   '})
    raw_key = authenticated_client.session['new_api_key']
    authenticated_client.post(reverse('create_api_key'), {'name': 'n' * 150})

    unnamed = ApiKey.objects.get(owner=authenticated_user, name='未命名')
    assert unnamed.prefix == raw_key[:8]
    assert unnamed.key_hash == hash_api_key(raw_key)
    assert ApiKey.objects.filter(owner=authenticated_user, name='n' * 100).exists()


@pytest.mark.django_db
def test_api_keys_page_shows_usage(authenticated_client, settings):
    """管理頁顯示目前數量 / 上限"""
    settings.USER_MAX_API_KEYS = 7

    response = authenticated_client.get(reverse('api_keys'))

    assert response.context['max_api_keys'] == 7
    assert '（0 / 7）' in response.content.decode()


@pytest.mark.django_db
def test_delete_api_key_get_does_not_delete(authenticated_client, authenticated_user, make_api_key):
    """GET 撤銷端點只會導回管理頁，金鑰仍存在"""
    api_key, _ = make_api_key(authenticated_user)

    response = authenticated_client.get(reverse('delete_api_key', args=[api_key.id]))

    assert response.status_code == 302
    assert response.url == reverse('api_keys')
    assert ApiKey.objects.filter(pk=api_key.pk).exists()


@pytest.mark.django_db
def test_delete_api_key_shows_message(authenticated_client, authenticated_user, make_api_key):
    """撤銷成功後導回管理頁並顯示訊息"""
    api_key, _ = make_api_key(authenticated_user)

    response = authenticated_client.post(
        reverse('delete_api_key', args=[api_key.id]), follow=True
    )

    assert response.redirect_chain[-1][0] == reverse('api_keys')
    assert [str(m) for m in response.context['messages']] == ['API Key 已撤銷']


@pytest.mark.django_db
def test_delete_api_key_only_target(authenticated_client, authenticated_user, make_api_key):
    """有多把金鑰時只撤銷指定的那一把"""
    keep, _ = make_api_key(authenticated_user, name='keep')
    drop, _ = make_api_key(authenticated_user, name='drop')

    authenticated_client.post(reverse('delete_api_key', args=[drop.id]))

    assert list(ApiKey.objects.filter(owner=authenticated_user)) == [keep]


@pytest.mark.django_db
def test_create_api_key_without_name_field(authenticated_client, authenticated_user):
    """表單沒有 name 欄位（例如直接 POST）也能建立，名稱為「未命名」"""
    response = authenticated_client.post(reverse('create_api_key'))

    assert response.status_code == 302
    assert ApiKey.objects.get(owner=authenticated_user).name == '未命名'
