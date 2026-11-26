import json
from typing import Any
from uuid import UUID

import pika
from pika.exceptions import AMQPError

from kubo_compute.models import OutboxEvent


class BrokerUnavailable(RuntimeError):
    pass


class RabbitMQ:
    def __init__(self, url: str, queue: str) -> None:
        if not url:
            raise RuntimeError("Compute broker URL is not configured.")
        if not queue.strip():
            raise RuntimeError("Compute broker queue is not configured.")
        self._queue = queue
        self._connection = pika.BlockingConnection(pika.URLParameters(url))
        self.channel = self._connection.channel()
        dead_exchange = f"{queue}.dead"
        dead_queue = f"{queue}.dead"
        self.channel.exchange_declare(exchange=dead_exchange, exchange_type="direct", durable=True)
        self.channel.queue_declare(queue=dead_queue, durable=True)
        self.channel.queue_bind(exchange=dead_exchange, queue=dead_queue, routing_key=dead_queue)
        self.channel.queue_declare(
            queue=queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": dead_exchange,
                "x-dead-letter-routing-key": dead_queue,
            },
        )
        self.channel.confirm_delivery()

    def __enter__(self) -> RabbitMQ:
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._connection.is_open:
            self._connection.close()

    def publish(self, event: OutboxEvent) -> None:
        body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        try:
            confirmed = self.channel.basic_publish(
                exchange="",
                routing_key=self._queue,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=str(event.operation_id),
                    type=event.event_type,
                ),
                mandatory=True,
            )
        except (AMQPError, OSError) as exc:
            raise BrokerUnavailable("RabbitMQ did not confirm the outbox event.") from exc
        if confirmed is not True:
            raise BrokerUnavailable("RabbitMQ did not confirm the outbox event.")

    def consume(self, callback: Any) -> None:
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=self._queue, on_message_callback=callback, auto_ack=False)
        self.channel.start_consuming()
