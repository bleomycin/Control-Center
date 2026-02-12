from django.db import models
from django.urls import reverse


COLOR_CHOICES = [
    ("red", "Red"), ("orange", "Orange"), ("yellow", "Yellow"),
    ("green", "Green"), ("blue", "Blue"), ("indigo", "Indigo"),
    ("purple", "Purple"), ("pink", "Pink"), ("cyan", "Cyan"), ("gray", "Gray"),
]


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default="blue")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            n = 1
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Folder(models.Model):
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default="blue")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Note(models.Model):
    NOTE_TYPE_CHOICES = [
        ("call", "Call"),
        ("email", "Email"),
        ("meeting", "Meeting"),
        ("research", "Research"),
        ("legal_update", "Legal Update"),
        ("general", "General"),
    ]

    title = models.CharField(max_length=255)
    content = models.TextField()
    date = models.DateTimeField(db_index=True)
    note_type = models.CharField(max_length=30, default="general")
    is_pinned = models.BooleanField(default=False)
    tags = models.ManyToManyField("Tag", blank=True, related_name="notes")
    folder = models.ForeignKey("Folder", on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    participants = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="notes_as_participant",
    )
    related_stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="notes",
    )
    related_legal_matters = models.ManyToManyField(
        "legal.LegalMatter", blank=True, related_name="notes",
    )
    related_properties = models.ManyToManyField(
        "assets.RealEstate", blank=True, related_name="notes",
    )
    related_investments = models.ManyToManyField(
        "assets.Investment", blank=True, related_name="notes",
    )
    related_loans = models.ManyToManyField(
        "assets.Loan", blank=True, related_name="notes",
    )
    related_tasks = models.ManyToManyField(
        "tasks.Task", blank=True, related_name="notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("notes:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["-date"]


class Attachment(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/")
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description or self.file.name

    def get_absolute_url(self):
        return reverse("notes:detail", kwargs={"pk": self.note.pk})


class Link(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="links")
    url = models.URLField(max_length=2000)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description

    def get_absolute_url(self):
        return reverse("notes:detail", kwargs={"pk": self.note.pk})
