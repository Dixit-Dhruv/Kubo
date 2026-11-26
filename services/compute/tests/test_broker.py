import json
from uuid import uuid4
from unittest.mock import Mock

import pika
import pytest

from kubo_compute.broker import BrokerUnavailable, RabbitMQ
from kubo_compute.models import OutboxEvent


def event() -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        operation_id=uuid4(),
        event_type="compute.operation.requested",
        payload={"operation_id": str(uuid4())},
    )


def test_rabbit_publisher_declares_durable_topology_and_publishes_persistent_message(monkeypatch):
    channel = Mock()
    channel.basic_publish.return_value = True
    connection = Mock()
    connection.channel.return_value = channel
    connection.is_open = True
    monkeypatch.setattr(pika, "BlockingConnection", lambda _parameters: connection)

    broker = RabbitMQ("amqp://guest:guest@localhost:5672/%2F", "compute.queue")
    item = event()
    broker.publish(item)

    channel.exchange_declare.assert_called_once_with(
        exchange="compute.queue.dead",
        exchange_type="direct",
        durable=True,
    )
    channel.confirm_delivery.assert_called_once_with()
    call = channel.basic_publish.call_args.kwargs
    assert call["routing_key"] == "compute.queue"
    assert call["mandatory"] is True
    assert call["properties"].delivery_mode == 2
    assert json.loads(call["body"]) == item.payload
    broker.close()
    connection.close.assert_called_once_with()


def test_rabbit_publisher_rejects_unconfirmed_message(monkeypatch):
    channel = Mock()
    channel.basic_publish.return_value = False
    connection = Mock()
    connection.channel.return_value = channel
    monkeypatch.setattr(pika, "BlockingConnection", lambda _parameters: connection)
    broker = RabbitMQ("amqp://guest:guest@localhost:5672/%2F", "compute.queue")

    with pytest.raises(BrokerUnavailable):
        broker.publish(event())
