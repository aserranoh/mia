
import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field
import logging
from typing import Callable

from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg


logger = logging.getLogger("Bus")


@dataclass
class Bus:
    """A simple wrapper around a NATS client to manage connection and message publishing."""

    nats_server: str = "nats://127.0.0.1:4222"

    _client: NatsClient = field(init=False, default_factory=NatsClient)
    _pending_subscriptions: list[tuple[str, Callable[[Msg], Awaitable[None]]]] = field(
        init=False,
        default_factory=list,
    )
    _subscription_lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        """Start the bus by connecting to NATS."""
        asyncio.create_task(self._connect_loop())

    async def publish(self, subject: str, data: bytes):
        """Publish a message to the given subject on NATS."""
        print(f"Publishing to {subject}: {len(data)}...")  # Debug print
        if not self._client.is_connected:
            logger.error("Cannot publish to NATS: not connected")
            return
        await self._client.publish(subject, data)

    async def subscribe(self, subject: str, callback: Callable[[Msg], Awaitable[None]]):
        """Subscribe now if connected, otherwise queue and apply on connect/reconnect."""
        async with self._subscription_lock:
            if not self._client.is_connected:
                self._enqueue_pending_subscription(subject, callback)
                logger.info("Queued subscription for %s (NATS not connected yet)", subject)
                return
        try:
            await self._client.subscribe(subject, cb=callback)
        except Exception as exc:
            logger.warning("Subscription to %s failed, queueing for retry: %s", subject, exc)
            async with self._subscription_lock:
                self._enqueue_pending_subscription(subject, callback)

    async def _connect_loop(self):
        """Continuously attempt to connect to NATS, with a delay between attempts."""
        while True:
            try:
                await self._client.connect(
                    servers=self.nats_server,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                    disconnected_cb=self._on_disconnected,
                    reconnected_cb=self._on_reconnected,
                    error_cb=self._on_error,
                    closed_cb=self._on_closed,
                )
                logger.info("Connected to NATS at %s", self.nats_server)
                await self._apply_pending_subscriptions()
                return  # exit loop once connected
            except Exception as exc:
                logger.warning("Failed to connect to NATS at %s: %s", self.nats_server, exc)
                await asyncio.sleep(2)

    async def _on_disconnected(self):
        """Handle NATS disconnection events."""
        logger.warning("Disconnected from %s", self.nats_server)

    async def _on_reconnected(self):
        """Handle NATS reconnection events."""
        logger.info("Reconnected to %s", self.nats_server)
        await self._apply_pending_subscriptions()

    async def _on_error(self, exc: Exception):
        """Handle NATS error events."""
        logger.error(str(exc))

    async def _on_closed(self):
        """Handle NATS connection closed events."""
        logger.error("Connection permanently closed")

    def _enqueue_pending_subscription(self, subject: str, callback: Callable[[Msg], Awaitable[None]]) -> None:
        """Store subscription intent once; duplicates are ignored."""
        subscription = (subject, callback)
        if subscription not in self._pending_subscriptions:
            self._pending_subscriptions.append(subscription)

    async def _apply_pending_subscriptions(self) -> None:
        """Attempt to apply queued subscriptions while connected."""
        async with self._subscription_lock:
            if not self._client.is_connected or not self._pending_subscriptions:
                return
            pending = self._pending_subscriptions
            self._pending_subscriptions = []

        failed: list[tuple[str, Callable[[Msg], Awaitable[None]]]] = []
        for subject, callback in pending:
            try:
                await self._client.subscribe(subject, cb=callback)
                logger.info("Applied pending subscription for %s", subject)
            except Exception as exc:
                logger.warning("Failed to apply pending subscription for %s: %s", subject, exc)
                failed.append((subject, callback))

        if failed:
            async with self._subscription_lock:
                for subject, callback in failed:
                    self._enqueue_pending_subscription(subject, callback)