from __future__ import annotations

import asyncio
import os
from logging import getLogger
from typing import TYPE_CHECKING

import msgspec
from aio_pika import Channel, DeliveryMode, Message, connect_robust
from aio_pika.pool import Pool

from utils.maps import MapModel

from ..newsfeed import NewsfeedEvent
from .models import BulkArchiveMapBody, MapSubmissionBody

if TYPE_CHECKING:
    from aio_pika.abc import AbstractIncomingMessage, AbstractQueue, AbstractRobustConnection

    import core

log = getLogger(__name__)

rabbitmq_user = os.getenv("RABBITMQ_DEFAULT_USER")
rabbitmq_pass = os.getenv("RABBITMQ_DEFAULT_PASS")


class Rabbit:
    _queue: AbstractQueue
    _queue_creation_task: asyncio.Task

    def __init__(self, bot: core.Genji) -> None:
        self._bot = bot
        self._connection_pool = Pool(self.get_connection, max_size=2)
        self._channel_pool = Pool(self.get_channel, max_size=10)
        self._queue_creation_task = asyncio.create_task(self._set_up_queue())

    async def _set_up_queue(self) -> None:
        log.debug("[x] [RabbitMQ] Setting up queue.")
        channel = await self.get_channel()
        await channel.set_qos(prefetch_count=1)
        self._queue = await channel.declare_queue(
            "genjiapi",
            durable=True,
        )
        log.debug("[x] [RabbitMQ] Consume queue start.")
        await self._queue.consume(self._process_message)

    @staticmethod
    async def get_connection() -> AbstractRobustConnection:
        try:
            return await connect_robust(
                f"amqp://{rabbitmq_user}:{rabbitmq_pass}@genji-rabbit/",
            )
        except Exception as e:
            log.error(f"[!] [RabbitMQ] Error connecting get_connection: {e}")
            raise e

    async def get_channel(self) -> Channel:
        try:
            async with self._connection_pool.acquire() as connection:
                return await connection.channel()
        except Exception as e:
            log.error(f"[!] [RabbitMQ] Error getting channel get_channel: {e}")
            raise e

    async def publish(self, queue_name: str, json_data: bytes) -> None:
        async with self._channel_pool.acquire() as channel:
            message = Message(json_data, delivery_mode=DeliveryMode.PERSISTENT)
            await channel.default_exchange.publish(message, routing_key=queue_name)
            log.debug(f"[x] [RabbitMQ] Published message to {queue_name}:\n{message}")

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process():
            x_type = message.headers["x-type"]
            if message.headers.get("x-test-mode"):
                return
            assert isinstance(x_type, str)
            match x_type:
                case "playtest":
                    decoded_json = msgspec.json.decode(message.body, type=MapModel)
                    # _data = decoded_json.rabbit_data
                    await self._bot.playtest_manager.add_playtest(decoded_json)
                    # TODO: Check if MOD, else send to playtestmanager
                    return
                case "bulk_archive" | "bulk_unarchive":
                    decoded_json = msgspec.json.decode(message.body, type=list[BulkArchiveMapBody])
                    _data = [_d.rabbit_data for _d in decoded_json]
                case "legacy":
                    ...
                    # decoded_json = msgspec.json.decode(message.body, type=BulkLegacyBody)
                case _:
                    return

            event = NewsfeedEvent(x_type, _data)
            await self._bot.genji_dispatch.handle_event(event, self._bot)
