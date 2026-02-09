from django.db import models
from django.urls import reverse


class LegalMatter(models.Model):
    MATTER_TYPE_CHOICES = [
        ("litigation", "Litigation"),
        ("compliance", "Compliance"),
        ("investigation", "Investigation"),
        ("transaction", "Transaction"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("pending", "Pending"),
        ("resolved", "Resolved"),
        ("on_hold", "On Hold"),
    ]

    title = models.CharField(max_length=255)
    case_number = models.CharField(max_length=100, blank=True)
    matter_type = models.CharField(max_length=20, choices=MATTER_TYPE_CHOICES, default="other")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    jurisdiction = models.CharField(max_length=255, blank=True)
    court = models.CharField(max_length=255, blank=True)
    filing_date = models.DateField(null=True, blank=True)
    next_hearing_date = models.DateField(null=True, blank=True)
    settlement_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    judgment_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    outcome = models.TextField(blank=True)
    description = models.TextField(blank=True)
    attorneys = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="legal_matters_as_attorney",
    )
    related_stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="legal_matters",
    )
    related_properties = models.ManyToManyField(
        "assets.RealEstate", blank=True, related_name="legal_matters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("legal:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["-created_at"]


class Evidence(models.Model):
    legal_matter = models.ForeignKey(LegalMatter, on_delete=models.CASCADE, related_name="evidence")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    evidence_type = models.CharField(max_length=100, blank=True)
    date_obtained = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="evidence/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("legal:detail", kwargs={"pk": self.legal_matter.pk})

    class Meta:
        verbose_name_plural = "Evidence"
        ordering = ["-date_obtained"]
