from django.db import models
from django.urls import reverse


class AssetTab(models.Model):
    ASSET_TYPE_CHOICES = [
        ("properties", "Properties"),
        ("investments", "Investments"),
        ("loans", "Loans"),
        ("policies", "Policies"),
        ("vehicles", "Vehicles"),
        ("aircraft", "Aircraft"),
    ]

    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    asset_types = models.JSONField(default=list, blank=True,
                                   help_text="List of asset type values for this tab")
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
            while AssetTab.objects.filter(key=key).exclude(pk=self.pk).exists():
                key = f"{base_key}-{n}"
                n += 1
            self.key = key
        super().save(*args, **kwargs)


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
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="PropertyOwnership",
        related_name="properties",
        blank=True,
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


class PropertyOwnership(models.Model):
    """Through model for RealEstate-Stakeholder M2M with ownership details."""
    property = models.ForeignKey(RealEstate, on_delete=models.CASCADE, related_name="ownerships")
    stakeholder = models.ForeignKey("stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="property_ownerships")
    ownership_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ownership percentage (e.g., 50.00 for 50%)"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Owner, Co-owner, Partner")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Property ownerships"
        ordering = ["-ownership_percentage", "stakeholder__name"]
        unique_together = [("property", "stakeholder")]

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"

    def get_notes_url(self):
        return reverse("assets:ownership_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-ownership-{self.pk}"


class Investment(models.Model):
    name = models.CharField(max_length=255)
    investment_type = models.CharField(max_length=100, blank=True)
    institution = models.CharField(max_length=255, blank=True)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="InvestmentParticipant",
        related_name="investments",
        blank=True,
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


class InvestmentParticipant(models.Model):
    """Through model for Investment-Stakeholder M2M with participation details."""
    investment = models.ForeignKey(Investment, on_delete=models.CASCADE, related_name="participants")
    stakeholder = models.ForeignKey("stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="investment_participations")
    ownership_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ownership percentage (e.g., 50.00 for 50%)"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Investor, Co-investor, Fund Manager")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Investment participants"
        ordering = ["-ownership_percentage", "stakeholder__name"]
        unique_together = [("investment", "stakeholder")]

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"

    def get_notes_url(self):
        return reverse("assets:participant_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-participant-{self.pk}"


class Loan(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("paid_off", "Paid Off"),
        ("defaulted", "Defaulted"),
        ("in_dispute", "In Dispute"),
    ]

    name = models.CharField(max_length=255)
    related_property = models.ForeignKey(
        RealEstate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="loans", verbose_name="Property",
    )
    related_investment = models.ForeignKey(
        Investment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="loans", verbose_name="Investment",
    )
    related_vehicle = models.ForeignKey(
        "Vehicle", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="loans", verbose_name="Vehicle",
    )
    related_aircraft = models.ForeignKey(
        "Aircraft", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="loans", verbose_name="Aircraft",
    )
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="LoanParty",
        related_name="loans",
        blank=True,
    )
    borrower_description = models.CharField(max_length=255, blank=True)
    original_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    default_interest_rate = models.DecimalField(
        "Default interest rate (%)", max_digits=6, decimal_places=3,
        null=True, blank=True,
        help_text="Rate applied when loan is in default",
    )
    is_hard_money = models.BooleanField("Hard money loan", default=False)
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


class LoanParty(models.Model):
    """Through model for Loan-Stakeholder M2M with party details."""
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="parties")
    stakeholder = models.ForeignKey("stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="loan_parties")
    ownership_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ownership/liability percentage (e.g., 50.00 for 50%)"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Lender, Borrower, Co-borrower, Guarantor")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Loan parties"
        ordering = ["role", "-ownership_percentage", "stakeholder__name"]
        unique_together = [("loan", "stakeholder")]

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"

    def get_notes_url(self):
        return reverse("assets:loan_party_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-party-{self.pk}"


class InsurancePolicy(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
        ("pending", "Pending"),
    ]

    PREMIUM_FREQUENCY_CHOICES = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("semi_annual", "Semi-Annual"),
        ("annual", "Annual"),
    ]

    name = models.CharField(max_length=255)
    policy_number = models.CharField(max_length=100, blank=True)
    policy_type = models.CharField(max_length=30, default="general")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    carrier = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="policies_as_carrier",
        verbose_name="Carrier",
    )
    agent = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="policies_as_agent",
        verbose_name="Agent",
    )
    premium_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    premium_frequency = models.CharField(
        max_length=20, choices=PREMIUM_FREQUENCY_CHOICES, default="annual", blank=True,
    )
    deductible = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coverage_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    covered_properties = models.ManyToManyField(
        RealEstate, blank=True, related_name="insurance_policies",
    )
    covered_vehicles = models.ManyToManyField(
        "Vehicle", blank=True, related_name="insurance_policies",
    )
    covered_aircraft = models.ManyToManyField(
        "Aircraft", blank=True, related_name="insurance_policies",
    )
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="PolicyHolder",
        related_name="insurance_policies",
        blank=True,
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:policy_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name_plural = "Insurance policies"
        ordering = ["name"]


class PolicyHolder(models.Model):
    """Through model for InsurancePolicy-Stakeholder M2M with role details."""
    policy = models.ForeignKey(InsurancePolicy, on_delete=models.CASCADE, related_name="policyholders")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="policyholder_roles",
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Named Insured, Beneficiary, Additional Insured")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Policy holders"
        ordering = ["role", "stakeholder__name"]
        unique_together = [("policy", "stakeholder")]

    def __str__(self):
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{role}"

    def get_notes_url(self):
        return reverse("assets:policyholder_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-holder-{self.pk}"


class Vehicle(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("stored", "Stored"),
        ("sold", "Sold"),
        ("in_dispute", "In Dispute"),
    ]

    name = models.CharField(max_length=255)
    vin = models.CharField("VIN", max_length=50, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    make = models.CharField(max_length=100, blank=True)
    model_name = models.CharField("Model", max_length=100, blank=True)
    vehicle_type = models.CharField(max_length=30, default="other")
    color = models.CharField(max_length=50, blank=True)
    license_plate = models.CharField(max_length=20, blank=True)
    registration_state = models.CharField(max_length=50, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True)
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="VehicleOwner",
        related_name="vehicles",
        blank=True,
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:vehicle_detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["name"]


class VehicleOwner(models.Model):
    """Through model for Vehicle-Stakeholder M2M with ownership details."""
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="owners")
    stakeholder = models.ForeignKey("stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="vehicle_ownerships")
    ownership_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ownership percentage (e.g., 50.00 for 50%)"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Owner, Co-owner")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Vehicle owners"
        ordering = ["-ownership_percentage", "stakeholder__name"]
        unique_together = [("vehicle", "stakeholder")]

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"

    def get_notes_url(self):
        return reverse("assets:vehicle_owner_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-vowner-{self.pk}"


class Aircraft(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("in_maintenance", "In Maintenance"),
        ("stored", "Stored"),
        ("sold", "Sold"),
        ("in_dispute", "In Dispute"),
    ]

    name = models.CharField(max_length=255)
    tail_number = models.CharField("Tail Number", max_length=20, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    make = models.CharField(max_length=100, blank=True)
    model_name = models.CharField("Model", max_length=100, blank=True)
    aircraft_type = models.CharField(max_length=30, default="single_engine")
    num_engines = models.PositiveSmallIntegerField(null=True, blank=True)
    base_airport = models.CharField("Base Airport", max_length=10, blank=True)
    total_hours = models.DecimalField("Total Hours", max_digits=10, decimal_places=1, null=True, blank=True)
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    registration_country = models.CharField(max_length=50, blank=True, default="US")
    stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder",
        through="AircraftOwner",
        related_name="aircraft_owned",
        blank=True,
    )
    notes_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("assets:aircraft_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name_plural = "Aircraft"
        ordering = ["name"]


class AircraftOwner(models.Model):
    """Through model for Aircraft-Stakeholder M2M with ownership details."""
    aircraft = models.ForeignKey(Aircraft, on_delete=models.CASCADE, related_name="owners")
    stakeholder = models.ForeignKey("stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="aircraft_ownerships")
    ownership_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ownership percentage (e.g., 50.00 for 50%)"
    )
    role = models.CharField(max_length=100, blank=True, help_text="e.g., Owner, Co-owner, Operator")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Aircraft owners"
        ordering = ["-ownership_percentage", "stakeholder__name"]
        unique_together = [("aircraft", "stakeholder")]

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"

    def get_notes_url(self):
        return reverse("assets:aircraft_owner_notes", kwargs={"pk": self.pk})

    def get_notes_id(self):
        return f"notes-aowner-{self.pk}"
