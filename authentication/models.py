from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class CustomUserManager(UserManager):
    """Ensure superusers are always treated as admins in this app."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('status', 'active')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return super().create_superuser(username, email=email, password=password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('admin', 'Administrator'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    student_code = models.CharField(max_length=30, unique=True, blank=True, null=True)
    department = models.CharField(max_length=120, blank=True)
    course_year = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = CustomUserManager()
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def is_admin(self):
        """Check if user is an admin"""
        return self.role == 'admin'
    
    @property
    def is_student(self):
        """Check if user is a student"""
        return self.role == 'student'
    
    @property
    def is_active_user(self):
        """Check if user account is active"""
        return self.status == 'active'

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def identifier(self):
        return self.student_code or f"S{self.id:03d}"


class SanctionType(models.Model):
    GRAVITY_CHOICES = (
        ("Minor", "Minor"),
        ("Major", "Major"),
        ("Grave", "Grave"),
    )

    description = models.CharField(max_length=255, unique=True)
    hours = models.PositiveIntegerField(default=1)
    gravity = models.CharField(max_length=10, choices=GRAVITY_CHOICES, default="Minor")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["description"]

    def __str__(self):
        return self.description

    @property
    def gravity_class(self):
        return self.gravity.lower()


class Sanction(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("completed", "Completed"),
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sanctions")
    sanction_type = models.ForeignKey(
        SanctionType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sanctions",
    )
    violation_snapshot = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=120, blank=True)
    required_hours = models.PositiveIntegerField(default=0)
    completed_hours = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    date_issued = models.DateField()
    due_date = models.DateField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_issued", "-created_at"]

    def __str__(self):
        return f"{self.student.display_name} - {self.violation}"

    def save(self, *args, **kwargs):
        if self.sanction_type and not self.violation_snapshot:
            self.violation_snapshot = self.sanction_type.description

        if self.required_hours and self.completed_hours >= self.required_hours:
            self.status = "completed"
        elif self.status == "completed" and self.completed_hours < self.required_hours:
            self.status = "active"
        super().save(*args, **kwargs)

    @property
    def violation(self):
        if self.sanction_type_id:
            return self.sanction_type.description
        return self.violation_snapshot or "Unknown"

    @property
    def student_name(self):
        return self.student.display_name

    @property
    def student_id(self):
        return self.student.identifier

    @property
    def status_label(self):
        return self.get_status_display()

    @property
    def status_class(self):
        return self.status

    @property
    def progress_percent(self):
        if not self.required_hours:
            return 0
        return min(int((self.completed_hours / self.required_hours) * 100), 100)


class ServiceHourSubmission(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="service_submissions")
    sanction = models.ForeignKey(
        Sanction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_submissions",
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_service_submissions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    proof = models.FileField(upload_to="service_hours/proofs/", blank=True, null=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.student.display_name} - {self.hours}h ({self.get_status_display()})"

    @property
    def status_class(self):
        return f"status-{self.status}"

    @property
    def proof_url(self):
        return self.proof.url if self.proof else ""


class Concern(models.Model):
    TOPIC_CHOICES = (
        ("Duplicate Sanction", "Duplicate Sanction"),
        ("Incorrect Sanction", "Incorrect Sanction"),
        ("Issue with Service Hours", "Issue with Service Hours"),
        ("My Status is Incorrect", "My Status is Incorrect"),
        ("Other", "Other"),
    )
    STATUS_CHOICES = (
        ("new", "New"),
        ("progress", "In Progress"),
        ("resolved", "Resolved"),
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="concerns")
    subject = models.CharField(max_length=120, choices=TOPIC_CHOICES)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.display_name} - {self.subject}"

    @property
    def status_label(self):
        return self.get_status_display()

    @property
    def status_class(self):
        return self.status
