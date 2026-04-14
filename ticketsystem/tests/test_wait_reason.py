"""Tests for Ticket.wait_reason behavior on status changes."""
import pytest
from enums import TicketStatus, WaitReason
from services.ticket_core_service import TicketCoreService
from exceptions import DomainError
from models import Ticket, db


@pytest.fixture
def wartet_ticket(app):
    with app.app_context():
        t = Ticket(title="WR-Test", status=TicketStatus.OFFEN.value)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    yield tid


def test_wartet_without_reason_raises(app, wartet_ticket):
    with app.app_context():
        with pytest.raises(DomainError) as exc:
            TicketCoreService.update_status(
                wartet_ticket, TicketStatus.WARTET, author_name="t"
            )
        assert getattr(exc.value, "field", None) == "wait_reason"


def test_wartet_with_reason_persists(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KUNDE.value,
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason == "kunde"


def test_leaving_wartet_clears_reason(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KOLLEGE.value,
        )
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.IN_BEARBEITUNG, author_name="t",
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason is None


def test_invalid_wait_reason_raises(app, wartet_ticket):
    with app.app_context():
        with pytest.raises(DomainError):
            TicketCoreService.update_status(
                wartet_ticket, TicketStatus.WARTET, author_name="t",
                wait_reason="mondphase",
            )


def test_changing_wait_reason_while_wartet_updates(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KUNDE.value,
        )
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.LIEFERANT.value,
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason == "lieferant"
