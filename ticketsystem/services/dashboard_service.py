"""Dashboard queries, project summaries, and workload overview.

Extracted from the monolithic ``ticket_service.py`` to isolate
read-heavy dashboard logic into a dedicated service module.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from enums import ELEVATED_ROLES, TicketStatus
from extensions import db
from models import ChecklistItem, Comment, Team, Ticket, TicketContact, Worker
from utils import get_utc_now

from ._ticket_helpers import (
    TicketFilterSpec,
    _OPEN_STATUSES,
    _confidential_filter,
    _is_critical_ticket,
    _team_clauses,
    _workload_sort_key,
    apply_search_filter,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _base_ticket_query() -> Any:
    """Return the base query with eager-loading for dashboard use."""
    return Ticket.query.filter_by(is_deleted=False).options(
        selectinload(Ticket.comments),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_team),
        selectinload(Ticket.tags),
        selectinload(Ticket.checklists),
    )


def _apply_assignment_filters(
    query: Any,
    worker_id: Optional[int],
    team_ids: Optional[List[int]],
    assigned_to_me: bool,
    unassigned_only: bool,
    assigned_worker_id: Optional[int],
) -> Any:
    """Apply assignment-related filters to a ticket query."""
    if assigned_to_me and worker_id:
        tc = _team_clauses(team_ids)
        query = query.filter(
            db.or_(
                Ticket.assigned_to_id == worker_id,
                Ticket.checklists.any(
                    db.and_(
                        ChecklistItem.assigned_to_id == worker_id,
                        ChecklistItem.is_completed.is_(False),
                    )
                ),
                *tc,
            )
        )
    elif unassigned_only:
        query = query.filter(
            Ticket.assigned_to_id.is_(None),
            Ticket.assigned_team_id.is_(None),
        )

    if assigned_worker_id:
        query = query.filter(
            Ticket.assigned_to_id == int(assigned_worker_id)
        )
    return query


def _fetch_summary_counts(
    worker_id: Optional[int],
    worker_role: Optional[str],
    team_ids: Optional[List[int]],
) -> Dict[str, Any]:
    """Fetch status counts and action-driven counts for the dashboard."""
    base_filter = Ticket.is_deleted.is_(False)
    confidential = (
        db.or_(*_confidential_filter(worker_id, team_ids))
        if worker_role not in ELEVATED_ROLES and worker_id is not None
        else None
    )

    # Status counts
    counts_query = (
        db.session.query(Ticket.status, func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
    )
    if confidential is not None:
        counts_query = counts_query.filter(confidential)
    counts = counts_query.group_by(Ticket.status).all()
    summary: Dict[str, Any] = {s: 0 for s in _OPEN_STATUSES}
    for status, count in counts:
        summary[status] = count

    # Unassigned count
    unassigned_q = (
        db.session.query(func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
        .filter(Ticket.assigned_to_id.is_(None))
        .filter(Ticket.assigned_team_id.is_(None))
    )
    if confidential is not None:
        unassigned_q = unassigned_q.filter(confidential)
    summary["unassigned"] = unassigned_q.scalar() or 0

    # Callback pending count
    callback_q = (
        db.session.query(func.count(Ticket.id))
        .filter(base_filter)
        .filter(Ticket.status.in_(_OPEN_STATUSES))
        .filter(Ticket.contact.has(TicketContact.callback_requested.is_(True)))
    )
    if confidential is not None:
        callback_q = callback_q.filter(confidential)
    summary["callback_pending"] = callback_q.scalar() or 0

    return summary


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _finalize_projects(
    projects: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Compute progress percentages and sort the project list."""
    result: List[Dict[str, Any]] = []
    for project in projects.values():
        total = project["total_tickets"]
        project["progress"] = (
            int((project["ticket_progress_sum"] / total) * 100)
            if total > 0
            else 0
        )
        project["is_completed"] = project["progress"] == 100
        result.append(project)

    result.sort(
        key=lambda x: (
            x["is_completed"],
            -(x["last_updated"].timestamp() if x["last_updated"] else 0),
        )
    )
    return result


# ---------------------------------------------------------------------------
# Workload helpers
# ---------------------------------------------------------------------------

def _group_tickets_by_worker(
    tickets: List[Ticket],
) -> Dict[int, Set[Ticket]]:
    """Group tickets by assigned worker (including team members)."""
    by_worker: Dict[int, Set[Ticket]] = {}
    for ticket in tickets:
        if ticket.assigned_to_id:
            by_worker.setdefault(ticket.assigned_to_id, set()).add(ticket)
        if ticket.assigned_team_id and ticket.assigned_team:
            for member in ticket.assigned_team.members:
                by_worker.setdefault(member.id, set()).add(ticket)
    return by_worker


def _build_workload_entry(
    worker: Worker,
    worker_tickets: List[Ticket],
    today: date,
    week_end: date,
) -> Dict[str, Any]:
    """Build a workload summary dict for a single worker."""
    critical = [t for t in worker_tickets if _is_critical_ticket(t, week_end)]
    other = [t for t in worker_tickets if not _is_critical_ticket(t, week_end)]

    critical.sort(key=lambda t: _workload_sort_key(t, today))
    other.sort(key=lambda t: _workload_sort_key(t, today))

    return {
        "worker": worker,
        "open_count": len(worker_tickets),
        "critical_count": len(critical),
        "tickets": critical + other,
        "critical_tickets": critical,
        "other_tickets": other,
    }


# ---------------------------------------------------------------------------
# Main Service Class
# ---------------------------------------------------------------------------

class DashboardService:
    """Dashboard queries, project summaries, and workload overview."""

    @staticmethod
    def get_dashboard_tickets(f: TicketFilterSpec) -> Dict[str, Any]:
        """Fetch tickets for the dashboard with filtering and pagination."""
        query = _base_ticket_query()
        is_elevated = f.worker_role in ELEVATED_ROLES

        # Confidential filter
        if not is_elevated and f.worker_id is not None:
            query = query.filter(
                db.or_(*_confidential_filter(f.worker_id, f.team_ids))
            )

        # Assignment filters
        query = _apply_assignment_filters(
            query, f.worker_id, f.team_ids,
            f.assigned_to_me, f.unassigned_only, f.assigned_worker_id,
        )

        # Callback filter
        if f.callback_pending:
            query = query.filter(
                Ticket.contact.has(TicketContact.callback_requested.is_(True)),
                Ticket.status != TicketStatus.ERLEDIGT.value,
            )

        # Date range
        if f.start_date:
            query = query.filter(Ticket.created_at >= f.start_date)
        if f.end_date:
            query = query.filter(Ticket.created_at < f.end_date)

        # Due-within-days filter
        if f.due_within_days > 0:
            cutoff = (date.today() + timedelta(days=f.due_within_days))
            query = query.filter(
                Ticket.due_date.isnot(None),
                Ticket.due_date <= cutoff,
            )

        # Author filter
        if f.author_name:
            author_sub = (
                db.session.query(Comment.ticket_id)
                .filter(
                    Comment.event_type == "TICKET_CREATED",
                    Comment.author.ilike(f"%{f.author_name}%"),
                )
                .subquery()
            )
            query = query.filter(Ticket.id.in_(author_sub))

        # Full-text search
        if f.search:
            query = apply_search_filter(query, f.search)

        # Status filter
        if f.status_filter:
            query = query.filter(Ticket.status == f.status_filter)
        elif not f.search and not f.assigned_to_me:
            query = query.filter(
                Ticket.status != TicketStatus.ERLEDIGT.value
            )

        # Dynamic sorting
        _SORT_COLUMNS = {
            "id": Ticket.id,
            "title": Ticket.title,
            "priority": Ticket.priority,
            "status": Ticket.status,
            "created_at": Ticket.created_at,
            "due_date": Ticket.due_date,
            "order_reference": Ticket.order_reference,
        }
        if f.sort_by and f.sort_by in _SORT_COLUMNS:
            col = _SORT_COLUMNS[f.sort_by]
            if f.sort_dir == "asc":
                order = col.asc().nullslast()
            else:
                order = col.desc().nullslast()
            focus_pagination = query.order_by(
                order, Ticket.id.desc()
            ).paginate(page=f.page, per_page=f.per_page, error_out=False)
        else:
            focus_pagination = query.order_by(
                Ticket.priority.asc(), Ticket.created_at.desc()
            ).paginate(page=f.page, per_page=f.per_page, error_out=False)

        summary_counts = _fetch_summary_counts(
            f.worker_id, f.worker_role, f.team_ids,
        )

        return {
            "focus_pagination": focus_pagination,
            "summary_counts": summary_counts,
        }

    @staticmethod
    def get_projects_summary() -> List[Dict[str, Any]]:
        """Fetch projects grouped by order_reference with progress.

        Uses a single SQL query with GROUP BY instead of loading full ORM
        objects, avoiding N+1 on checklists.
        """
        from sqlalchemy import Float, case, cast

        # Checklist done/total per ticket as subquery
        ci = (
            db.session.query(
                ChecklistItem.ticket_id.label("tid"),
                func.count(ChecklistItem.id).label("total"),
                func.sum(
                    case((ChecklistItem.is_completed.is_(True), 1), else_=0)
                ).label("done"),
            )
            .group_by(ChecklistItem.ticket_id)
            .subquery()
        )

        rows = (
            db.session.query(
                Ticket.order_reference,
                Ticket.status,
                func.count(Ticket.id).label("cnt"),
                func.max(
                    func.coalesce(Ticket.updated_at, Ticket.created_at)
                ).label("last_upd"),
                func.sum(
                    case(
                        (
                            ci.c.total > 0,
                            cast(ci.c.done, Float) / cast(ci.c.total, Float),
                        ),
                        (Ticket.status == TicketStatus.ERLEDIGT.value, 1.0),
                        else_=0.0,
                    )
                ).label("progress_sum"),
            )
            .outerjoin(ci, Ticket.id == ci.c.tid)
            .filter(
                Ticket.is_deleted.is_(False),
                Ticket.order_reference.isnot(None),
                Ticket.order_reference != "",
            )
            .group_by(Ticket.order_reference, Ticket.status)
            .all()
        )

        projects: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ref = row.order_reference.strip()
            if not ref:
                continue
            if ref not in projects:
                projects[ref] = {
                    "order_reference": ref,
                    "total_tickets": 0,
                    "completed_tickets": 0,
                    "last_updated": None,
                    "ticket_progress_sum": 0.0,
                    "status_counts": {s.value: 0 for s in TicketStatus},
                }
            p = projects[ref]
            p["total_tickets"] += row.cnt
            p["status_counts"][row.status] = (
                p["status_counts"].get(row.status, 0) + row.cnt
            )
            if row.status == TicketStatus.ERLEDIGT.value:
                p["completed_tickets"] += row.cnt
            p["ticket_progress_sum"] += row.progress_sum or 0.0
            if row.last_upd and (
                not p["last_updated"] or row.last_upd > p["last_updated"]
            ):
                p["last_updated"] = row.last_upd

        return _finalize_projects(projects)

    @staticmethod
    def get_workload_overview() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return workload entries split into absent and present workers."""
        now = get_utc_now()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=4)

        tickets = (
            Ticket.query.filter(
                Ticket.is_deleted.is_(False),
                Ticket.status.in_(_OPEN_STATUSES),
                db.or_(
                    Ticket.assigned_to_id.isnot(None),
                    Ticket.assigned_team_id.isnot(None),
                ),
            )
            .options(
                joinedload(Ticket.assigned_to),
                selectinload(Ticket.assigned_team).selectinload(Team.members),
                selectinload(Ticket.checklists),
            )
            .all()
        )

        tickets_by_worker = _group_tickets_by_worker(tickets)
        workers = Worker.query.filter_by(is_active=True).all()

        absent: List[Dict[str, Any]] = []
        present: List[Dict[str, Any]] = []

        for worker in workers:
            worker_tickets = list(tickets_by_worker.get(worker.id, []))
            if not worker_tickets:
                continue

            entry = _build_workload_entry(
                worker, worker_tickets, today, week_end
            )
            if worker.is_out_of_office:
                absent.append(entry)
            else:
                present.append(entry)

        absent.sort(
            key=lambda x: (-x["critical_count"], -x["open_count"])
        )
        present.sort(key=lambda x: -x["open_count"])
        return absent, present
