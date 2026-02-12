from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse


class StakeholderTab(models.Model):
    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    entity_types = models.JSONField(default=list, blank=True,
                                    help_text="List of entity_type values for this tab")
    sort_order = models.PositiveIntegerField(default=0)
    is_builtin = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        if not self.key:
            from django.utils.text import slugify
            base_key = slugify(self.label)
            key = base_key
            n = 1
            while StakeholderTab.objects.filter(key=key).exclude(pk=self.pk).exists():
                key = f"{base_key}-{n}"
                n += 1
            self.key = key
        super().save(*args, **kwargs)


class Stakeholder(models.Model):
    ENTITY_TYPE_CHOICES = [
        ("advisor", "Advisor"),
        ("business_partner", "Business Partner"),
        ("lender", "Lender"),
        ("contact", "Contact"),
        ("professional", "Professional"),
        ("attorney", "Attorney"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255, db_index=True)
    entity_type = models.CharField(max_length=30, default="contact", db_index=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    organization = models.CharField(max_length=255, blank=True)
    trust_rating = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    risk_rating = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    parent_organization = models.ForeignKey(
        "self", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="employees",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("stakeholders:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class Relationship(models.Model):
    from_stakeholder = models.ForeignKey(
        Stakeholder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="relationships_from",
    )
    to_stakeholder = models.ForeignKey(
        Stakeholder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="relationships_to",
    )
    relationship_type = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.from_stakeholder} → {self.to_stakeholder} ({self.relationship_type})"

    def get_absolute_url(self):
        if self.from_stakeholder:
            return reverse("stakeholders:detail", kwargs={"pk": self.from_stakeholder.pk})
        return reverse("stakeholders:list")

    class Meta:
        unique_together = ["from_stakeholder", "to_stakeholder", "relationship_type"]


class ContactLog(models.Model):
    METHOD_CHOICES = [
        ("call", "Call"),
        ("email", "Email"),
        ("text", "Text"),
        ("meeting", "Meeting"),
        ("other", "Other"),
    ]

    stakeholder = models.ForeignKey(Stakeholder, on_delete=models.SET_NULL, null=True, blank=True, related_name="contact_logs")
    date = models.DateTimeField()
    method = models.CharField(max_length=30)
    summary = models.TextField()
    follow_up_needed = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.stakeholder} - {self.method} on {self.date:%Y-%m-%d}"

    def get_absolute_url(self):
        if self.stakeholder:
            return reverse("stakeholders:detail", kwargs={"pk": self.stakeholder.pk})
        return reverse("stakeholders:list")

    class Meta:
        ordering = ["-date"]
