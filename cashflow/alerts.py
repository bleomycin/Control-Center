from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from assets.models import Loan
from cashflow.models import CashFlowEntry


def get_liquidity_alerts():
    """Calculate liquidity alerts based on current cash flow data and upcoming payments."""
    alerts = []
    today = timezone.localdate()

    # 1. Net negative flow — current month actual net flow < $0
    current_month_entries = CashFlowEntry.objects.filter(
        date__year=today.year,
        date__month=today.month,
        is_projected=False,
    )
    totals = current_month_entries.aggregate(
        inflows=Sum("amount", filter=Q(entry_type="inflow"), default=Decimal("0")),
        outflows=Sum("amount", filter=Q(entry_type="outflow"), default=Decimal("0")),
    )
    net = totals["inflows"] - totals["outflows"]
    if net < 0:
        alerts.append({
            "level": "critical",
            "title": "Negative Net Cash Flow",
            "message": f"This month's actual net flow is -${abs(net):,.0f}. "
                       f"Outflows (${totals['outflows']:,.0f}) exceed inflows (${totals['inflows']:,.0f}).",
        })

    # 2. Large upcoming loan payments — due within 30 days totaling > $5,000
    upcoming_cutoff = today + timedelta(days=30)
    upcoming_loans = Loan.objects.filter(
        status="active",
        next_payment_date__gte=today,
        next_payment_date__lte=upcoming_cutoff,
        monthly_payment__isnull=False,
    )
    total_payments = upcoming_loans.aggregate(
        total=Sum("monthly_payment", default=Decimal("0"))
    )["total"]
    if total_payments > 5000:
        count = upcoming_loans.count()
        alerts.append({
            "level": "warning",
            "title": "Large Upcoming Payments",
            "message": f"${total_payments:,.0f} in loan payments due within 30 days "
                       f"across {count} loan{'s' if count != 1 else ''}.",
        })

    # 3. Projected shortfall — projected outflows exceed projected inflows for next 30 days
    projected_entries = CashFlowEntry.objects.filter(
        date__gte=today,
        date__lte=upcoming_cutoff,
        is_projected=True,
    )
    proj_totals = projected_entries.aggregate(
        inflows=Sum("amount", filter=Q(entry_type="inflow"), default=Decimal("0")),
        outflows=Sum("amount", filter=Q(entry_type="outflow"), default=Decimal("0")),
    )
    proj_net = proj_totals["inflows"] - proj_totals["outflows"]
    if proj_net < 0:
        alerts.append({
            "level": "warning",
            "title": "Projected Shortfall",
            "message": f"Projected outflows exceed inflows by ${abs(proj_net):,.0f} over the next 30 days.",
        })

    return alerts
