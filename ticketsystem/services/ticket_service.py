"""Backward-compatible facade for ticket operations.

This module used to be the monolithic service (1 747 lines).  All logic has
been extracted into focused modules:

* ``ticket_core_service``      -- CRUD, notifications, comments, status
* ``ticket_assignment_service`` -- assignment and OOO delegation
* ``ticket_approval_service``   -- approval workflow
* ``checklist_service``         -- checklist item operations
* ``dashboard_service``         -- dashboard queries, projects, workload

The ``TicketService`` class below delegates every method to the appropriate
new service, so existing call-sites (routes, scheduler, etc.) continue to
work without changes.

Dataclasses (``TicketFilterSpec``, ``ContactInfo``) and frequently used
helpers are re-exported from ``_ticket_helpers`` so that existing imports
like ``from services.ticket_service import TicketFilterSpec`` keep working.
"""

# Re-export dataclasses (routes import them from here)
from ._ticket_helpers import ContactInfo, TicketFilterSpec  # noqa: F401

# Re-export constants and helpers consumed by external modules
from ._ticket_helpers import (  # noqa: F401
    _OPEN_STATUSES,
    _RECURRENCE_INCREMENTS,
    _confidential_filter,
    _urgency_score,
)

from .checklist_service import ChecklistService
from .dashboard_service import DashboardService
from .ticket_approval_service import TicketApprovalService
from .ticket_assignment_service import TicketAssignmentService
from .ticket_core_service import TicketCoreService


class TicketService:
    """Backward-compatible facade -- delegates to focused service modules."""

    # Expose urgency_score as a class attribute (used by scheduler)
    _urgency_score = staticmethod(_urgency_score)

    # ------------------------------------------------------------------
    # Core (ticket_core_service)
    # ------------------------------------------------------------------

    create_ticket = staticmethod(TicketCoreService.create_ticket)
    update_ticket = staticmethod(TicketCoreService.update_ticket)
    delete_ticket = staticmethod(TicketCoreService.delete_ticket)
    create_notification = staticmethod(TicketCoreService.create_notification)
    add_comment = staticmethod(TicketCoreService.add_comment)
    update_status = staticmethod(TicketCoreService.update_status)
    update_ticket_meta = staticmethod(TicketCoreService.update_ticket_meta)

    # ------------------------------------------------------------------
    # Assignment (ticket_assignment_service)
    # ------------------------------------------------------------------

    _resolve_delegation = staticmethod(TicketAssignmentService._resolve_delegation)
    assign_ticket = staticmethod(TicketAssignmentService.assign_ticket)
    reassign_ticket = staticmethod(TicketAssignmentService.reassign_ticket)

    # ------------------------------------------------------------------
    # Approval (ticket_approval_service)
    # ------------------------------------------------------------------

    get_pending_approvals = staticmethod(TicketApprovalService.get_pending_approvals)
    request_approval = staticmethod(TicketApprovalService.request_approval)
    approve_ticket = staticmethod(TicketApprovalService.approve_ticket)
    reject_ticket = staticmethod(TicketApprovalService.reject_ticket)

    # ------------------------------------------------------------------
    # Checklists (checklist_service)
    # ------------------------------------------------------------------

    add_checklist_item = staticmethod(ChecklistService.add_checklist_item)
    toggle_checklist_item = staticmethod(ChecklistService.toggle_checklist_item)
    delete_checklist_item = staticmethod(ChecklistService.delete_checklist_item)
    apply_checklist_template = staticmethod(ChecklistService.apply_checklist_template)

    # ------------------------------------------------------------------
    # Dashboard (dashboard_service)
    # ------------------------------------------------------------------

    get_dashboard_tickets = staticmethod(DashboardService.get_dashboard_tickets)
    get_projects_summary = staticmethod(DashboardService.get_projects_summary)
    get_workload_overview = staticmethod(DashboardService.get_workload_overview)
