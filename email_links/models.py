from django.db import models


class EmailLink(models.Model):
    """Links a Gmail message to one or more entities. No email body is stored."""

    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    subject = models.CharField(max_length=500, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(max_length=255, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    message_count = models.PositiveIntegerField(default=1)
    provider = models.CharField(max_length=50, default="gmail")

    # Entity links (nullable FKs — same pattern as Document)
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_investment = models.ForeignKey(
        "assets.Investment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_loan = models.ForeignKey(
        "assets.Loan", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_lease = models.ForeignKey(
        "assets.Lease", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_policy = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_vehicle = models.ForeignKey(
        "assets.Vehicle", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_aircraft = models.ForeignKey(
        "assets.Aircraft", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_legal_matter = models.ForeignKey(
        "legal.LegalMatter", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_note = models.ForeignKey(
        "notes.Note", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )
    related_task = models.ForeignKey(
        "tasks.Task", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="email_links",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return self.subject or self.message_id

    @property
    def web_url(self):
        """Construct a Gmail web link from the message_id."""
        return f"https://mail.google.com/mail/u/0/#all/{self.message_id}"

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
        if self.related_note:
            links.append(("Note", self.related_note))
        if self.related_task:
            links.append(("Task", self.related_task))
        return links
