from django.db import models
from django.urls import reverse
from django.utils import timezone


class HealthcareTab(models.Model):
    HEALTHCARE_TYPE_CHOICES = [
        ("providers", "Providers"),
        ("prescriptions", "Prescriptions"),
        ("supplements", "Supplements"),
        ("test_results", "Test Results"),
        ("visits", "Visits"),
        ("advice", "Advice"),
        ("appointments", "Appointments"),
        ("conditions", "Conditions"),
    ]

    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    healthcare_types = models.JSONField(default=list, blank=True,
                                        help_text="List of healthcare type values for this tab")
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
            while HealthcareTab.objects.filter(key=key).exclude(pk=self.pk).exists():
                key = f"{base_key}-{n}"
                n += 1
            self.key = key
        super().save(*args, **kwargs)


class Provider(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("past", "Past"),
    ]

    name = models.CharField(max_length=255)
    provider_type = models.CharField(max_length=30, default="primary_care")
    specialty = models.CharField(max_length=255, blank=True)
    practice_name = models.CharField(max_length=255, blank=True)
    npi = models.CharField("NPI", max_length=20, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    fax = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="healthcare_providers",
    )
    health_insurance = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="healthcare_providers",
        verbose_name="Insurance Policy",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("healthcare:provider_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class Condition(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("managed", "Managed"),
        ("resolved", "Resolved"),
        ("monitoring", "Monitoring"),
    ]

    SEVERITY_CHOICES = [
        ("mild", "Mild"),
        ("moderate", "Moderate"),
        ("severe", "Severe"),
    ]

    name = models.CharField(max_length=255)
    icd_code = models.CharField("ICD Code", max_length=20, blank=True)
    diagnosed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, blank=True)
    diagnosed_by = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="diagnosed_conditions",
    )
    description = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("healthcare:condition_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class Prescription(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("discontinued", "Discontinued"),
        ("on_hold", "On Hold"),
    ]

    FREQUENCY_CHOICES = [
        ("once_daily", "Once Daily"),
        ("twice_daily", "Twice Daily"),
        ("three_daily", "Three Times Daily"),
        ("four_daily", "Four Times Daily"),
        ("as_needed", "As Needed"),
        ("weekly", "Weekly"),
        ("biweekly", "Biweekly"),
        ("monthly", "Monthly"),
        ("other", "Other"),
    ]

    medication_name = models.CharField(max_length=255)
    generic_name = models.CharField(max_length=255, blank=True)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, blank=True)
    route = models.CharField(max_length=50, blank=True, help_text="e.g., oral, topical, injection")
    pharmacy = models.CharField(max_length=255, blank=True)
    pharmacy_phone = models.CharField(max_length=30, blank=True)
    rx_number = models.CharField("Rx Number", max_length=50, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    refills_total = models.PositiveIntegerField(null=True, blank=True)
    refills_remaining = models.PositiveIntegerField(null=True, blank=True)
    next_refill_date = models.DateField(null=True, blank=True)
    is_controlled = models.BooleanField("Controlled substance", default=False)
    purpose = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    prescribing_provider = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="prescriptions",
    )
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="prescriptions",
    )
    health_insurance = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="covered_prescriptions",
        verbose_name="Insurance Policy",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.medication_name

    def get_absolute_url(self):
        return reverse("healthcare:prescription_detail", kwargs={"pk": self.pk})

    @property
    def is_refill_due(self):
        if not self.next_refill_date:
            return False
        return self.next_refill_date <= timezone.localdate()

    class Meta:
        ordering = ["medication_name"]


class Supplement(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("paused", "Paused"),
        ("discontinued", "Discontinued"),
    ]

    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=20, choices=Prescription.FREQUENCY_CHOICES, blank=True)
    purpose = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    recommended_by = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="recommended_supplements",
    )
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="supplements",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("healthcare:supplement_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class TestResult(models.Model):
    STATUS_CHOICES = [
        ("normal", "Normal"),
        ("abnormal", "Abnormal"),
        ("critical", "Critical"),
        ("pending", "Pending"),
        ("inconclusive", "Inconclusive"),
    ]

    test_name = models.CharField(max_length=255)
    test_type = models.CharField(max_length=30, default="lab")
    date = models.DateField(db_index=True)
    facility = models.CharField(max_length=255, blank=True)
    result_value = models.CharField(max_length=255, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    result_summary = models.TextField(blank=True)
    file = models.FileField(upload_to="test_results/", blank=True)
    gdrive_url = models.URLField(max_length=500, blank=True, verbose_name="Google Drive URL")
    ordering_provider = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ordered_tests",
    )
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="test_results",
    )
    health_insurance = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="covered_tests",
        verbose_name="Insurance Policy",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_drive_link(self):
        return bool(self.gdrive_url)

    def __str__(self):
        return self.test_name

    def get_absolute_url(self):
        return reverse("healthcare:testresult_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["-date"]


class Visit(models.Model):
    VISIT_TYPE_CHOICES = [
        ("routine", "Routine"),
        ("follow_up", "Follow-Up"),
        ("urgent", "Urgent"),
        ("specialist", "Specialist"),
        ("telehealth", "Telehealth"),
        ("procedure", "Procedure"),
        ("other", "Other"),
    ]

    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True)
    provider = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="visits",
    )
    facility = models.CharField(max_length=255, blank=True)
    visit_type = models.CharField(max_length=20, choices=VISIT_TYPE_CHOICES, default="routine")
    reason = models.CharField(max_length=255, blank=True)
    diagnosis = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    vitals = models.TextField(blank=True, help_text="BP, HR, weight, temp, etc.")
    follow_up_instructions = models.TextField(blank=True)
    next_visit_date = models.DateField(null=True, blank=True)
    copay = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="visits",
    )
    health_insurance = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="covered_visits",
        verbose_name="Insurance Policy",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        provider_name = self.provider.name if self.provider else "Unknown"
        return f"{self.get_visit_type_display()} — {provider_name} ({self.date})"

    def get_absolute_url(self):
        return reverse("healthcare:visit_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["-date"]


class Advice(models.Model):
    CATEGORY_CHOICES = [
        ("diet", "Diet"),
        ("exercise", "Exercise"),
        ("medication", "Medication"),
        ("lifestyle", "Lifestyle"),
        ("preventive", "Preventive"),
        ("follow_up", "Follow-Up"),
        ("restriction", "Restriction"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
        ("superseded", "Superseded"),
    ]

    title = models.CharField(max_length=255)
    advice_text = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    given_by = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="advice_given",
    )
    related_visit = models.ForeignKey(
        Visit, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="advice_records",
    )
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="advice_records",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("healthcare:advice_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name_plural = "Advice"
        ordering = ["-date"]


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
        ("rescheduled", "Rescheduled"),
    ]

    title = models.CharField(max_length=255)
    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    provider = models.ForeignKey(
        Provider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="appointments",
    )
    facility = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    url = models.URLField(max_length=2000, blank=True)
    visit_type = models.CharField(max_length=20, choices=Visit.VISIT_TYPE_CHOICES, default="routine")
    purpose = models.TextField(blank=True)
    preparation = models.TextField(blank=True, help_text="Fasting, bring records, etc.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    related_condition = models.ForeignKey(
        Condition, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="appointments",
    )
    health_insurance = models.ForeignKey(
        "assets.InsurancePolicy", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="healthcare_appointments",
        verbose_name="Insurance Policy",
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("healthcare:appointment_detail", kwargs={"pk": self.pk})

    @property
    def scheduled_datetime_str(self):
        if self.time:
            return f"{self.date.isoformat()}T{self.time.strftime('%H:%M:%S')}"
        return self.date.isoformat()

    class Meta:
        ordering = ["-date", "-time"]
