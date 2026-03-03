from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse


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

    name = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, default="contact")
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
        Stakeholder, on_delete=models.CASCADE, related_name="relationships_from"
    )
    to_stakeholder = models.ForeignKey(
        Stakeholder, on_delete=models.CASCADE, related_name="relationships_to"
    )
    relationship_type = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.from_stakeholder} → {self.to_stakeholder} ({self.relationship_type})"

    def get_absolute_url(self):
        return reverse("stakeholders:detail", kwargs={"pk": self.from_stakeholder.pk})

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

    stakeholder = models.ForeignKey(Stakeholder, on_delete=models.CASCADE, related_name="contact_logs")
    date = models.DateTimeField()
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    summary = models.TextField()
    follow_up_needed = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.stakeholder} - {self.method} on {self.date:%Y-%m-%d}"

    def get_absolute_url(self):
        return reverse("stakeholders:detail", kwargs={"pk": self.stakeholder.pk})

    class Meta:
        ordering = ["-date"]
