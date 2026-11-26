from datetime import UTC, datetime, timedelta
from uuid import UUID

from kubo_compute.catalog import ComputeProfile
from kubo_compute.models import ComputeOperation, OutboxEvent
from kubo_compute.operations import accept_create
from kubo_compute.outbox import publish_due_outbox_events
from kubo_compute.schemas import ComputeCreateRequest

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084")
ACTOR_ID = UUID("8c07034d-15ae-46cb-846b-fdb9911e637b")
PROFILE = ComputeProfile(
    cpu_millicores=500,
    memory_bytes=536870912,
    ephemeral_storage_bytes=1073741824,
)


def accept(session):
    return accept_create(
        session=session,
        organization_id=ORGANIZATION_ID,
        actor_id=ACTOR_ID,
        idempotency_key="publish-1",
        request=ComputeCreateRequest(name="web", image="approved-web", profile="small"),
        image_reference="registry.example.com/kubo/web@sha256:" + ("a" * 64),
        profile=PROFILE,
        now=NOW,
    )


def test_publisher_marks_event_only_after_confirmation(compute_session):
    accepted = accept(compute_session)
    observed_payloads = []

    published_count = publish_due_outbox_events(
        compute_session,
        lambda event: observed_payloads.append(event.payload),
        now=NOW,
    )

    event = compute_session.get(OutboxEvent, accepted.operation.outbox_event.id)
    assert published_count == 1
    assert observed_payloads == [{"operation_id": str(accepted.operation.id)}]
    assert event.published_at.replace(tzinfo=UTC) == NOW
    assert event.publish_attempts == 0


def test_publisher_persists_retry_delay_when_confirmation_fails(compute_session):
    accepted = accept(compute_session)

    def fail_publish(_event):
        from kubo_compute.broker import BrokerUnavailable

        raise BrokerUnavailable("not confirmed")

    published_count = publish_due_outbox_events(compute_session, fail_publish, now=NOW)

    event = compute_session.get(OutboxEvent, accepted.operation.outbox_event.id)
    assert published_count == 0
    assert event.published_at is None
    assert event.publish_attempts == 1
    assert event.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=1)


def test_publisher_replays_stale_running_operations(compute_session):
    accepted = accept(compute_session)
    operation = compute_session.get(ComputeOperation, accepted.operation.id)
    event = operation.outbox_event
    operation.status = "running"
    operation.attempt_count = 1
    operation.updated_at = NOW - timedelta(minutes=6)
    event.published_at = NOW - timedelta(minutes=6)
    compute_session.commit()
    payloads = []

    count = publish_due_outbox_events(compute_session, lambda row: payloads.append(row.payload), now=NOW)

    assert count == 1
    assert payloads == [{"operation_id": str(operation.id)}]
    assert event.published_at.replace(tzinfo=UTC) == NOW
