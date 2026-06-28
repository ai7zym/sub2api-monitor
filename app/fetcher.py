"""抓取核心：httpx 异步并发版本，支持 token 缓存复用。

抓取流程：
  1. 优先用缓存的 token 访问 /api/v1/keys
  2. token 失效（401 / 403）或缺失时重新 POST /api/v1/auth/login
  3. 返回抓取结果 + 需要更新的 token 映射
  4. 余额通过 GET /api/v1/auth/me 实时获取（不缓存）
"""
import asyncio
import logging
from typing import Optional

import httpx

from . import config

logger = logging.getLogger("price_monitor.fetcher")


def _make_result(site: dict, **overrides) -> dict:
    return {
        "site_id": site.get("id"),
        "domain": site["domain"],
        "balance": None,
        "group_name": None,
        "rate_multiplier": None,
        "key_name": None,
        "key_id": None,
        "key_status": None,
        "error": None,
        **overrides,
    }


async def _do_login(
    client: httpx.AsyncClient, site: dict
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """登录，返回 (token, balance, error_msg)。"""
    base_url = f"https://{site['domain']}"
    try:
        resp = await client.post(
            f"{base_url}/api/v1/auth/login",
            headers={"content-type": "application/json"},
            json={"email": site["email"], "password": site["password"]},
        )
    except Exception as e:  # noqa: BLE001
        return None, None, f"请求异常: {e}"

    if resp.status_code != 200:
        return None, None, f"HTTP {resp.status_code}"

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None, None, "登录响应非 JSON"

    if data.get("code") != 0:
        return None, None, data.get("message")

    token = data.get("data", {}).get("access_token")
    if not token:
        return None, None, "未获取到token"

    balance = data.get("data", {}).get("user", {}).get("balance")
    return token, balance, None


async def _fetch_balance(
    client: httpx.AsyncClient, site: dict
) -> Optional[float]:
    """通过 /api/v1/auth/me 获取用户实时余额。"""
    base_url = f"https://{site['domain']}"
    try:
        resp = await client.get(
            f"{base_url}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {site['token']}"},
            params={"timezone": "Asia/Shanghai"},
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("获取余额异常: %s", e)
        return None

    if resp.status_code != 200:
        logger.debug("获取余额失败: HTTP %d", resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None

    if data.get("code") != 0:
        return None

    return data.get("data", {}).get("balance")


async def _fetch_keys(
    client: httpx.AsyncClient, site: dict, balance: float | None
) -> list[dict]:
    """用 token 拉取 keys，token 失效返回空列表。"""
    base_url = f"https://{site['domain']}"
    try:
        resp = await client.get(
            f"{base_url}/api/v1/keys",
            headers={"Authorization": f"Bearer {site['token']}"},
            params={
                "page": 1,
                "page_size": 20,
                "sort_by": "created_at",
                "sort_order": "desc",
                "timezone": "Asia/Shanghai",
            },
        )
    except Exception as e:  # noqa: BLE001
        return [_make_result(site, balance=balance, error=f"请求异常: {e}")]

    # token 过期，需要重新登录
    if resp.status_code in (401, 403):
        return []

    if resp.status_code != 200:
        return [_make_result(site, balance=balance, error=f"HTTP {resp.status_code}")]

    try:
        keys_data = resp.json()
    except Exception:  # noqa: BLE001
        return [_make_result(site, balance=balance, error="keys响应非 JSON")]

    if keys_data.get("code") != 0:
        return [_make_result(site, balance=balance, error=keys_data.get("message"))]

    items = keys_data.get("data", {}).get("items", [])
    if not items:
        return [_make_result(site, balance=balance, error="没有keys数据")]

    results: list[dict] = []
    for item in items:
        group = item.get("group", {}) or {}
        results.append(
            _make_result(
                site,
                balance=balance,
                group_name=group.get("name"),
                rate_multiplier=group.get("rate_multiplier"),
                key_name=item.get("name"),
                key_id=item.get("id"),
                key_status=item.get("status"),
            )
        )
    return results


async def fetch_one(
    client: httpx.AsyncClient, site: dict
) -> tuple[list[dict], Optional[tuple[int, str]]]:
    """抓取单个站点，返回 (结果列表, (site_id, new_token) 或 None)。"""
    # 有缓存 token → 先用缓存的 token 拉余额和 keys
    if site.get("token"):
        # 实时获取余额
        balance = await _fetch_balance(client, site)
        results = await _fetch_keys(client, site, balance=balance)
        if results and not any(
            r.get("error") and "HTTP 4" not in str(r.get("error", ""))
            for r in results
        ):
            return results, None
        need_relogin = not results or any(
            r.get("error") for r in results if "HTTP 4" not in str(r.get("error", ""))
        )
        if not need_relogin and results:
            return results, None

    # 没有 token 或 token 失效 → 登录
    new_token, balance, login_err = await _do_login(client, site)
    if login_err:
        return [_make_result(site, error=login_err)], None

    site_with_token = {**site, "token": new_token}
    results = await _fetch_keys(client, site_with_token, balance=balance)
    return results, (site["id"], new_token)


async def fetch_all(
    sites: list[dict],
) -> tuple[list[dict], dict[int, str]]:
    """并发抓取所有站点，返回 (结果列表, {site_id: new_token})。"""
    if not sites:
        return [], {}

    semaphore = asyncio.Semaphore(config.FETCH_CONCURRENCY)
    timeout = httpx.Timeout(config.HTTP_TIMEOUT)

    token_updates: dict[int, str] = {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def _guarded(site: dict) -> tuple[list[dict], Optional[tuple[int, str]]]:
            async with semaphore:
                return await fetch_one(client, site)

        batches = await asyncio.gather(*(_guarded(s) for s in sites))

    results: list[dict] = []
    for batch, token_update in batches:
        results.extend(batch)
        if token_update:
            site_id, new_token = token_update
            token_updates[site_id] = new_token

    return results, token_updates


async def set_key_status(site: dict, key_id: int, status: str) -> bool:
    """调用上游 API 启用/禁用某个 key。
    
    site: {"domain", "token"}
    status: "active" 或 "inactive"
    """
    if not site.get("token"):
        logger.warning("set_key_status 失败: 站点 %s 无缓存 token", site.get("domain"))
        return False
    base_url = f"https://{site['domain']}"
    timeout = httpx.Timeout(config.HTTP_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.put(
                f"{base_url}/api/v1/keys/{key_id}",
                headers={
                    "Authorization": f"Bearer {site['token']}",
                    "content-type": "application/json",
                },
                json={"status": status},
            )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                logger.info("key %d 状态已设为 %s", key_id, status)
                return True
            logger.warning("设置 key %d 状态失败: %s", key_id, data.get("message"))
        else:
            logger.warning("设置 key %d 状态失败: HTTP %d", key_id, resp.status_code)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("设置 key %d 状态异常: %s", key_id, e)
        return False
