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
    matter_type = models.CharField(max_length=30, default="other")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
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
    related_investments = models.ManyToManyField(
        "assets.Investment", blank=True, related_name="legal_matters",
    )
    related_loans = models.ManyToManyField(
        "assets.Loan", blank=True, related_name="legal_matters",
    )
    related_vehicles = models.ManyToManyField(
        "assets.Vehicle", blank=True, related_name="legal_matters",
    )
    related_aircraft = models.ManyToManyField(
        "assets.Aircraft", blank=True, related_name="legal_matters",
    )
    related_policies = models.ManyToManyField(
        "assets.InsurancePolicy", blank=True, related_name="legal_matters",
    )
    related_leases = models.ManyToManyField(
        "assets.Lease", blank=True, related_name="legal_matters",
    )
    related_providers = models.ManyToManyField(
        "healthcare.Provider", blank=True, related_name="legal_matters",
    )
    related_prescriptions = models.ManyToManyField(
        "healthcare.Prescription", blank=True, related_name="legal_matters",
    )
    related_conditions = models.ManyToManyField(
        "healthcare.Condition", blank=True, related_name="legal_matters",
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
    gdrive_url = models.URLField(max_length=500, blank=True, verbose_name="Google Drive URL")
    url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def has_drive_link(self):
        return bool(self.gdrive_url)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("legal:detail", kwargs={"pk": self.legal_matter.pk})

    class Meta:
        verbose_name_plural = "Evidence"
        ordering = ["-date_obtained"]


class LegalCommunication(models.Model):
    DIRECTION_CHOICES = [
        ("outbound", "Outbound"),
        ("inbound", "Inbound"),
    ]
    legal_matter = models.ForeignKey(LegalMatter, on_delete=models.CASCADE, related_name="communications")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="legal_communications",
    )
    date = models.DateTimeField()
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default="outbound")
    method = models.CharField(max_length=30)
    subject = models.CharField(max_length=255, blank=True)
    summary = models.TextField()
    follow_up_needed = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_completed = models.BooleanField(default=False)
    follow_up_completed_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="communications/", blank=True)
    gdrive_url = models.URLField(max_length=500, blank=True, verbose_name="Google Drive URL")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def has_drive_link(self):
        return bool(self.gdrive_url)

    def __str__(self):
        return f"{self.get_direction_display()} {self.method} — {self.date:%Y-%m-%d}"

    def get_absolute_url(self):
        return reverse("legal:detail", kwargs={"pk": self.legal_matter.pk})

    class Meta:
        ordering = ["-date"]


class LegalChecklistItem(models.Model):
    legal_matter = models.ForeignKey(LegalMatter, on_delete=models.CASCADE, related_name="checklist_items")
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title


class CaseLog(models.Model):
    legal_matter = models.ForeignKey(LegalMatter, on_delete=models.CASCADE, related_name="case_logs")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="case_logs",
    )
    source_name = models.CharField(max_length=255, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_source(self):
        if self.stakeholder:
            return self.stakeholder.name
        return self.source_name or ""

    def __str__(self):
        return self.text[:80]

    def get_absolute_url(self):
        return reverse("legal:detail", kwargs={"pk": self.legal_matter.pk})

    class Meta:
        ordering = ["-created_at"]
