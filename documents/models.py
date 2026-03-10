from django.db import models


class Document(models.Model):
    """General-purpose document metadata record, optionally linked to Google Drive."""

    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)

    # Google Drive fields
    gdrive_file_id = models.CharField(
        "Google Drive File ID", max_length=255, blank=True, db_index=True,
    )
    gdrive_url = models.URLField("Google Drive URL", max_length=500, blank=True)
    gdrive_mime_type = models.CharField(max_length=100, blank=True)
    gdrive_file_name = models.CharField(
        "Original filename", max_length=255, blank=True,
    )

    # Local file fallback
    file = models.FileField(upload_to="documents/", blank=True)

    # Entity links (nullable FKs — same pattern as CashFlowEntry)
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_investment = models.ForeignKey(
        "assets.Investment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_loan = models.ForeignKey(
        "assets.Loan", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_lease = models.ForeignKey(
        "assets.Lease", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_policy = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_vehicle = models.ForeignKey(
        "assets.Vehicle", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_aircraft = models.ForeignKey(
        "assets.Aircraft", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )
    related_legal_matter = models.ForeignKey(
        "legal.LegalMatter", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documents",
    )

    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("documents:detail", args=[self.pk])

    @property
    def has_drive_link(self):
        return bool(self.gdrive_url)

    @property
    def has_file(self):
        return bool(self.file)

    @property
    def file_url(self):
        """Return the best available file URL (Drive preferred over local)."""
        if self.gdrive_url:
            return self.gdrive_url
        if self.file:
            return self.file.url
        return ""

    @property
    def is_expired(self):
        if not self.expiration_date:
            return False
        from django.utils import timezone
        return self.expiration_date < timezone.localdate()

    @property
    def is_expiring_soon(self):
        if not self.expiration_date:
            return False
        import datetime
        from django.utils import timezone
        today = timezone.localdate()
        return today <= self.expiration_date <= today + datetime.timedelta(days=90)

    @property
    def linked_entities(self):
        """Return list of (label, object) for all linked entities."""
        links = []
        if self.related_property:
            links.append(("Property", self.related_property))
        if self.related_investment:
            links.append(("Investment", self.related_investment))
        if self.related_loan:
            links.append(("Loan", self.related_loan))
        if self.related_lease:
            links.append(("Lease", self.related_lease))
        if self.related_policy:
            links.append(("Policy", self.related_policy))
        if self.related_vehicle:
            links.append(("Vehicle", self.related_vehicle))
        if self.related_aircraft:
            links.append(("Aircraft", self.related_aircraft))
        if self.related_stakeholder:
            links.append(("Stakeholder", self.related_stakeholder))
        if self.related_legal_matter:
            links.append(("Legal Matter", self.related_legal_matter))
        return links


class GoogleDriveSettings(models.Model):
    """Singleton (pk=1). Stores OAuth2 credentials and connection state."""

    is_connected = models.BooleanField(default=False)
    client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.CharField(max_length=255, blank=True)
    api_key = models.CharField(max_length=255, blank=True)
    refresh_token = models.TextField(blank=True)
    access_token = models.TextField(blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    connected_email = models.EmailField(blank=True)

    class Meta:
        verbose_name = "Google Drive Settings"
        verbose_name_plural = "Google Drive Settings"

    def __str__(self):
        if self.is_connected:
            return f"Google Drive (connected as {self.connected_email})"
        return "Google Drive (not connected)"

    @classmethod
    def load(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
