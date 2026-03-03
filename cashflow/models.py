from django.db import models
from django.urls import reverse


class CashFlowEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ("inflow", "Inflow"),
        ("outflow", "Outflow"),
    ]

    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    category = models.CharField(max_length=100, blank=True)
    date = models.DateField()
    is_projected = models.BooleanField(default=False)
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
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} ({self.entry_type}: ${self.amount})"

    def get_absolute_url(self):
        return reverse("cashflow:list")

    class Meta:
        verbose_name_plural = "Cash flow entries"
        ordering = ["-date"]
