from django.db import models
from django.urls import reverse


class RealEstate(models.Model):
    STATUS_CHOICES = [
        ("owned", "Owned"),
        ("under_contract", "Under Contract"),
        ("sold", "Sold"),
        ("in_dispute", "In Dispute"),
    ]

    name = models.CharField(max_length=255)
    address = models.TextField()
    jurisdiction = models.CharField(max_length=255, blank=True)
    property_type = models.CharField(max_length=100, blank=True)
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="owned")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="properties",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:realestate_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name_plural = "Real estate"
        ordering = ["name"]


class Investment(models.Model):
    name = models.CharField(max_length=255)
    investment_type = models.CharField(max_length=100, blank=True)
    institution = models.CharField(max_length=255, blank=True)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="investments",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:investment_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class Loan(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("paid_off", "Paid Off"),
        ("defaulted", "Defaulted"),
        ("in_dispute", "In Dispute"),
    ]

    name = models.CharField(max_length=255)
    lender = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="loans_as_lender",
    )
    borrower_description = models.CharField(max_length=255, blank=True)
    original_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_payment_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    collateral = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:loan_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]
