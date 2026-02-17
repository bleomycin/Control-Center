from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone


class CashFlowEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ("inflow", "Inflow"),
        ("outflow", "Outflow"),
    ]

    RECURRENCE_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("biweekly", "Biweekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
    ]

    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES, db_index=True)
    category = models.CharField(max_length=100, blank=True)
    date = models.DateField(db_index=True)
    is_projected = models.BooleanField(default=False)
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, blank=True)
    related_stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cash_flow_entries",
    )
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cash_flow_entries",
    )
    related_loan = models.ForeignKey(
        "assets.Loan", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cash_flow_entries",
    )
    related_investment = models.ForeignKey(
        "assets.Investment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cash_flow_entries",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} ({self.entry_type}: ${self.amount})"

    def get_absolute_url(self):
        return reverse("cashflow:detail", kwargs={"pk": self.pk})

    def create_next_recurrence(self):
        """Create the next recurring entry based on recurrence_rule."""
        if not self.is_recurring or not self.recurrence_rule:
            return None
        delta_map = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "biweekly": timedelta(weeks=2),
            "quarterly": timedelta(days=91),
            "yearly": timedelta(days=365),
        }
        if self.recurrence_rule == "monthly":
            month = self.date.month % 12 + 1
            year = self.date.year + (1 if month == 1 else 0)
            try:
                next_date = self.date.replace(year=year, month=month)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                next_date = self.date.replace(year=year, month=month, day=last_day)
        else:
            next_date = self.date + delta_map[self.recurrence_rule]
        return CashFlowEntry.objects.create(
            description=self.description,
            amount=self.amount,
            entry_type=self.entry_type,
            category=self.category,
            date=next_date,
            is_projected=self.is_projected,
            is_recurring=True,
            recurrence_rule=self.recurrence_rule,
            related_stakeholder=self.related_stakeholder,
            related_property=self.related_property,
            related_loan=self.related_loan,
            related_investment=self.related_investment,
            notes_text=self.notes_text,
        )

    class Meta:
        verbose_name_plural = "Cash flow entries"
        ordering = ["-date"]
