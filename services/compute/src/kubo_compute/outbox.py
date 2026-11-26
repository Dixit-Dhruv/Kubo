import logging
import time
from collections.abc import Callable
from datetime import datetime

import pika
from sqlalchemy import select
from sqlalchemy.orm import Session

from kubo_compute.broker import BrokerUnavailable, RabbitMQ
from kubo_compute.config import get_settings
from kubo_compute.database import SessionLocal
from kubo_compute.models import ComputeOperation, OperationStatus, OutboxEvent, utcnow
from kubo_compute.retries import OPERATION_LEASE, record_outbox_publish_failure

logger = logging.getLogger(__name__)
OUTBOX_BATCH_SIZE = 100
PUBLISH_IDLE_SECONDS = 1
BROKER_RECONNECT_SECONDS = 5


def publish_due_outbox_events(
    session: Session,
    publish: Callable[[OutboxEvent], None],
    now: datetime | None = None,
) -> int:
    published_at = now or utcnow()
    stale_events = session.scalars(
        select(OutboxEvent)
        .join(ComputeOperation, ComputeOperation.id == OutboxEvent.operation_id)
        .where(
            OutboxEvent.published_at.is_not(None),
            ComputeOperation.status == OperationStatus.RUNNING.value,
            ComputeOperation.updated_at <= published_at - OPERATION_LEASE,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for event in stale_events:
        event.published_at = None
        event.next_attempt_at = published_at
    session.flush()
    event_ids = list(
        session.scalars(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.next_attempt_at <= published_at,
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(OUTBOX_BATCH_SIZE)
        )
    )
    session.commit()
    published_count = 0

    for event_id in event_ids:
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.id == event_id,
                OutboxEvent.published_at.is_(None),
                OutboxEvent.next_attempt_at <= published_at,
            )
        )
        if event is None:
            session.rollback()
            continue
        try:
            publish(event)
        except BrokerUnavailable:
            record_outbox_publish_failure(event, published_at)
        else:
            event.published_at = published_at
            event.last_error_code = None
            published_count += 1
        session.commit()
    return published_count


def run() -> None:
    settings = get_settings()
    while True:
        try:
            with RabbitMQ(settings.broker_url, settings.broker_queue) as broker:
                while True:
                    with SessionLocal() as session:
                        published_count = publish_due_outbox_events(session, broker.publish)
                    if published_count == 0:
                        time.sleep(PUBLISH_IDLE_SECONDS)
        except (BrokerUnavailable, pika.exceptions.AMQPError, OSError):
            logger.error("RabbitMQ publisher unavailable; accepted outbox work remains durable.")
            time.sleep(BROKER_RECONNECT_SECONDS)
