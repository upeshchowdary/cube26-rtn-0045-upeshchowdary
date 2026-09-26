"""Webhook service and delivery dispatcher (§17 / P14)."""

from __future__ import annotations

import ipaddress
import json
import time
from urllib.parse import urlparse

import httpx

from returns_manager.ids import new_id
from returns_manager.webhooks.models import (
    WebhookDeliveryRecord,
    WebhookEvent,
    WebhookPayload,
    WebhookSubscription,
)
from returns_manager.webhooks.signer import compute_signature

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / AWS instance metadata
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def is_url_allowed(url: str, allowlist_str: str = "") -> tuple[bool, str]:
    """Validate webhook destination URL against SSRF rules and allowlist.

    Rules:
    - HTTPS is required in production; HTTP is allowed only for localhost / 127.0.0.1.
    - Cloud metadata (169.254.169.254) and private networks are blocked unless explicitly allowlisted.
    - If allowlist_str is non-empty, destination hostname must match an entry.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    if not parsed.scheme or not parsed.hostname:
        return False, "Missing URL scheme or hostname"

    is_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")

    if parsed.scheme == "http" and not is_local:
        return False, "HTTPS required for external webhooks"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    # Check IP restrictions for non-localhost
    if not is_local:
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            for net in _BLOCKED_NETWORKS:
                if ip in net:
                    return False, f"Destination IP {ip} is in restricted network {net}"
        except ValueError:
            # It's a domain name, not an IP literal
            pass

    # Check allowlist if configured
    if allowlist_str.strip():
        allowed_hosts = [h.strip().lower() for h in allowlist_str.split(",") if h.strip()]
        host_lower = parsed.hostname.lower()
        matched = False
        for allowed in allowed_hosts:
            if allowed == "*" or host_lower == allowed or host_lower.endswith("." + allowed):
                matched = True
                break
        if not matched:
            return False, f"Hostname {parsed.hostname} is not in RM_WEBHOOK_ALLOWLIST"

    return True, "ok"


class WebhookService:
    """Manages webhook subscriptions and delivers signed event payloads."""

    def __init__(self, allowlist: str = "") -> None:
        self.allowlist = allowlist
        self._subscriptions: dict[str, list[WebhookSubscription]] = {}  # org_id -> subs
        self._deliveries: list[WebhookDeliveryRecord] = []

    def register_subscription(
        self,
        *,
        org_id: str,
        url: str,
        secret: str,
        events: list[WebhookEvent] | None = None,
    ) -> WebhookSubscription:
        """Register a new webhook subscription for an organization."""
        allowed, reason = is_url_allowed(url, self.allowlist)
        if not allowed:
            raise ValueError(f"Webhook URL not allowed: {reason}")

        sub = WebhookSubscription(
            subscription_id=new_id(),
            org_id=org_id,
            url=url,
            secret=secret,
            events=events or ["evidence.finalized", "evidence.superseded"],
        )
        self._subscriptions.setdefault(org_id, []).append(sub)
        return sub

    def list_subscriptions(self, org_id: str) -> list[WebhookSubscription]:
        """List active subscriptions for an organization."""
        return [s for s in self._subscriptions.get(org_id, []) if s.is_active]

    def delete_subscription(self, org_id: str, subscription_id: str) -> bool:
        """Deactivate a webhook subscription."""
        subs = self._subscriptions.get(org_id, [])
        for s in subs:
            if s.subscription_id == subscription_id:
                s.is_active = False
                return True
        return False

    def list_deliveries(self, org_id: str) -> list[WebhookDeliveryRecord]:
        """Return history of delivery attempts for an org."""
        return [d for d in self._deliveries if d.org_id == org_id]

    async def dispatch(
        self,
        *,
        event: WebhookEvent,
        org_id: str,
        unit_id: str,
        record_id: str,
        record_version: int,
        document_sha256: str,
        links: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[WebhookDeliveryRecord]:
        """Dispatch event payload to all matching subscriptions for org_id."""
        subs = [s for s in self._subscriptions.get(org_id, []) if s.is_active and event in s.events]
        if not subs:
            return []

        payload = WebhookPayload(
            event=event,
            org_id=org_id,
            unit_id=unit_id,
            record_id=record_id,
            record_version=record_version,
            document_sha256=document_sha256,
            links=links
            or {
                "evidence": f"/api/v1/units/{unit_id}/return-evidence?version={record_version}",
                "chain": f"/api/v1/units/{unit_id}/chain/verification",
            },
        )
        body_bytes = json.dumps(payload.model_dump(), separators=(",", ":")).encode("utf-8")

        results: list[WebhookDeliveryRecord] = []
        owns_client = client is None
        http_client = client or httpx.AsyncClient(timeout=5.0)

        try:
            for sub in subs:
                sig_header = compute_signature(sub.secret, body_bytes)
                headers = {
                    "Content-Type": "application/json",
                    "RM-Signature": sig_header,
                    "User-Agent": "Returns-Manager-Webhook/1.0",
                }

                t0 = time.perf_counter()
                delivery = WebhookDeliveryRecord(
                    delivery_id=new_id(),
                    subscription_id=sub.subscription_id,
                    org_id=org_id,
                    event=event,
                    unit_id=unit_id,
                    url=sub.url,
                    success=False,
                )

                try:
                    resp = await http_client.post(sub.url, content=body_bytes, headers=headers)
                    delivery.duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    delivery.status_code = resp.status_code
                    delivery.success = 200 <= resp.status_code < 300
                except Exception as exc:
                    delivery.duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    delivery.error = str(exc)
                    delivery.success = False

                self._deliveries.append(delivery)
                results.append(delivery)
        finally:
            if owns_client:
                await http_client.aclose()

        return results


# Global singleton instance for application use
_default_webhook_service: WebhookService | None = None


def get_webhook_service(allowlist: str = "") -> WebhookService:
    global _default_webhook_service
    if _default_webhook_service is None:
        _default_webhook_service = WebhookService(allowlist=allowlist)
    return _default_webhook_service
