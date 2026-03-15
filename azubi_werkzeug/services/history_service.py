"""Service for handling History aggregation and session grouping."""
from enums import CheckType
from pdf_utils import parse_check_type


class HistoryService:
    """Service for handling History aggregation and session grouping."""

    @staticmethod
    def group_checks_into_sessions(all_checks):
        """Group flat check list into session dicts."""
        sessions_dict = HistoryService._aggregate_checks(all_checks)
        result = []
        for sd in sessions_dict.values():
            checks = sd['checks']
            raw_type = HistoryService._determine_session_type(checks)
            total = HistoryService._calculate_session_total(
                checks, raw_type, sd['is_payable']
            )

            result.append({
                'session_id': sd['session_id'],
                'datum': sd['datum'],
                'azubi_name': sd['azubi_name'],
                'is_ok': sd['is_ok'],
                'is_payable': sd['is_payable'],
                'total_price': total,
                'type': raw_type.value if hasattr(raw_type, 'value') else str(raw_type),
                'count': len(checks)
            })
        return result

    @staticmethod
    def _aggregate_checks(all_checks):
        """Aggregate checks into session buckets."""
        sessions_dict = {}
        for check in all_checks:
            sid = check.session_id if check.session_id else (
                f"LEGACY_{check.azubi_id}_{int(check.datum.timestamp())}"
            )
            if sid not in sessions_dict:
                sessions_dict[sid] = {
                    'session_id': check.session_id if check.session_id else sid,
                    'datum': check.datum,
                    'azubi_name': check.azubi.name,
                    'checks': [],
                    'is_ok': True,
                    'is_payable': False
                }

            s = sessions_dict[sid]
            s['checks'].append(check)

            bemerkung = (check.bemerkung or "").lower()
            if "status: missing" in bemerkung or "status: broken" in bemerkung:
                s['is_ok'] = False
            if "kostenpflichtig" in bemerkung:
                s['is_payable'] = True
        return sessions_dict

    @staticmethod
    def _determine_session_type(checks):
        """Determine the overall type of a check session."""
        from services.check_service import CheckService
        raw_type = CheckService.detect_exchange_type(checks)
        if raw_type:
            return raw_type

        # Fallback to homogeneity check
        types = {c.check_type for c in checks}
        if len(types) == 1:
            return parse_check_type(next(iter(types)))

        # Fallback to first check's type
        return parse_check_type(checks[0].check_type)

    @staticmethod
    def _calculate_session_total(checks, session_type, is_payable):
        """Calculate total price for a session."""
        if not is_payable:
            return 0.0
        total = 0.0
        for c in checks:
            c_type = parse_check_type(c.check_type)
            price_val = c.price if c.price is not None else (
                c.werkzeug.price if c.werkzeug else 0.0
            )
            if session_type == CheckType.EXCHANGE:
                if c_type == CheckType.ISSUE:
                    total += price_val
            else:
                total += price_val
        return total
