from django.db import models
from django.urls import reverse


class AssetTab(models.Model):
    ASSET_TYPE_CHOICES = [
        ("properties", "Properties"),
        ("investments", "Investments"),
        ("loans", "Loans"),
        ("policies", "Policies"),
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

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"


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

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"


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

    def __str__(self):
        percentage = f" ({self.ownership_percentage}%)" if self.ownership_percentage else ""
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{percentage}{role}"


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

    def __str__(self):
        role = f" - {self.role}" if self.role else ""
        return f"{self.stakeholder.name}{role}"
