"""Checklist operations: add, toggle, delete, and apply templates.

Extracted from the monolithic ``ticket_service.py`` to isolate
checklist management into a dedicated service module.
"""

import logging
from datetime import datetime
from typing import Optional

from enums import TicketStatus
from exceptions import DependencyNotMetError
from extensions import db
from models import ChecklistItem, Comment, Ticket

from ._helpers import db_transaction

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _check_dependency(item: ChecklistItem) -> None:
    """Raise if the item's dependency is not yet completed."""
    if not item.is_completed and item.depends_on_item_id:
        parent = db.session.get(ChecklistItem, item.depends_on_item_id)
        if parent and not parent.is_completed:
            raise DependencyNotMetError(
                f"Abhängigkeit nicht erfüllt: '{parent.title}' "
                "muss zuerst abgeschlossen werden."
            )


# ---------------------------------------------------------------------------
# Main Service Class
# ---------------------------------------------------------------------------

class ChecklistService:
    """Checklist item CRUD and template application."""

    @staticmethod
    @db_transaction
    def add_checklist_item(
        ticket_id: int,
        title: str,
        assigned_to_id: Optional[int] = None,
        assigned_team_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
        depends_on_item_id: Optional[int] = None,
    ) -> ChecklistItem:
        """Add a checklist item to a ticket."""
        item = ChecklistItem(
            ticket_id=ticket_id,
            title=title,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            due_date=due_date,
            depends_on_item_id=depends_on_item_id,
        )
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    @db_transaction
    def toggle_checklist_item(
        item_id: int,
        worker_name: str = "System",
        worker_id: Optional[int] = None,
    ) -> Optional[ChecklistItem]:
        """Toggle a checklist item and auto-close the ticket if all done."""
        item = db.session.get(ChecklistItem, item_id)
        if not item:
            return None

        _check_dependency(item)
        item.is_completed = not item.is_completed
        ticket = item.ticket

        if (
            item.is_completed
            and ticket.status != TicketStatus.ERLEDIGT.value
            and ticket.checklists
            and all(c.is_completed for c in ticket.checklists)
        ):
            ticket.status = TicketStatus.ERLEDIGT.value
            db.session.add(Comment(
                ticket_id=ticket.id,
                author=worker_name,
                author_id=worker_id,
                text=(
                    "Status automatisch auf ERLEDIGT gesetzt "
                    "(alle Unteraufgaben beendet)."
                ),
                is_system_event=True,
                event_type="STATUS_CHANGE",
            ))

        db.session.commit()
        return item

    @staticmethod
    @db_transaction
    def delete_checklist_item(item_id: int) -> bool:
        """Delete a checklist item (clears dependencies first)."""
        item = db.session.get(ChecklistItem, item_id)
        if item:
            ChecklistItem.query.filter_by(
                depends_on_item_id=item.id
            ).update({"depends_on_item_id": None})
            db.session.delete(item)
            db.session.commit()
        return True

    @staticmethod
    @db_transaction
    def reorder_items(ticket_id: int, item_order: list[int]) -> None:
        """Set the sort_order of checklist items for a ticket."""
        for idx, item_id in enumerate(item_order):
            item = db.session.get(ChecklistItem, item_id)
            if item and item.ticket_id == ticket_id:
                item.sort_order = idx
        db.session.commit()

    @staticmethod
    @db_transaction
    def apply_checklist_template(
        ticket_id: int, template_id: int, commit: bool = True
    ) -> bool:
        """Apply a checklist template to a ticket."""
        from exceptions import TicketNotFoundError
        from models import ChecklistTemplate

        ticket = db.session.get(Ticket, ticket_id)
        template = db.session.get(ChecklistTemplate, template_id)
        if not ticket or not template:
            raise TicketNotFoundError()

        ticket.checklist_template_id = template_id
        for t_item in template.items:
            db.session.add(ChecklistItem(
                ticket_id=ticket.id,
                title=t_item.title,
                is_completed=False,
            ))
        db.session.add(Comment(
            ticket_id=ticket.id,
            author="System",
            text=f"Checklisten-Vorlage '{template.title}' angewendet.",
            is_system_event=True,
            event_type="CHECKLIST_TEMPLATE_APPLIED",
        ))
        if commit:
            db.session.commit()
        return True
