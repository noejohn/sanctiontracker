from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from authentication.models import Concern, Sanction, SanctionType, ServiceHourSubmission, User

logger = logging.getLogger(__name__)


def has_admin_access(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or getattr(user, "role", None) == "admin"
    )


def parse_iso_date(raw_value, field_label):
    if not raw_value:
        raise ValueError(f"{field_label} is required.")
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_label} is invalid.") from exc


def parse_non_negative_int(raw_value, field_label, default=None):
    if raw_value in (None, ""):
        if default is not None:
            return default
        raise ValueError(f"{field_label} is required.")
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_label} must be a whole number.") from exc
    if parsed < 0:
        raise ValueError(f"{field_label} cannot be negative.")
    return parsed


def parse_decimal(raw_value, field_label):
    if raw_value in (None, ""):
        raise ValueError(f"{field_label} is required.")
    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_label} must be a number.") from exc
    if value <= 0:
        raise ValueError(f"{field_label} must be greater than zero.")
    return value


def format_hours(value):
    if value is None:
        return 0
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    rounded = value.quantize(Decimal("0.01"))
    if rounded == rounded.to_integral():
        return int(rounded)
    return float(rounded)


def normalize_gravity(raw_value):
    valid_gravity = {"minor": "Minor", "major": "Major", "grave": "Grave"}
    if not raw_value:
        return "Minor"
    return valid_gravity.get(raw_value.strip().lower(), "Minor")


def split_full_name(full_name):
    cleaned = (full_name or "").strip()
    if not cleaned:
        return "", ""
    parts = cleaned.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def build_unique_username(base_value):
    cleaned = "".join(ch for ch in (base_value or "").lower() if ch.isalnum() or ch in {"-", "_", "."})
    cleaned = cleaned[:140] or "student"
    candidate = cleaned
    counter = 1
    while User.objects.filter(username=candidate).exists():
        suffix = str(counter)
        candidate = f"{cleaned[:150 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def build_temp_password(seed):
    token = "".join(ch for ch in (seed or "") if ch.isalnum())
    token = (token[:6] or "Student").capitalize()
    return f"{token}@123Aa"


def format_activity_time(when):
    when_date = when.date() if isinstance(when, datetime) else when
    delta_days = (timezone.localdate() - when_date).days
    if delta_days <= 0:
        return "Today"
    if delta_days == 1:
        return "1 day ago"
    return f"{delta_days} days ago"


def attempt_student_password_change(request, current_password, new_password, confirm_password):
    """Validate and persist a password change initiated by a student."""
    user = request.user
    if not user.check_password(current_password):
        return False, "Current password is incorrect."
    if not new_password:
        return False, "New password cannot be empty."
    if new_password != confirm_password:
        return False, "New password confirmation does not match."

    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user)
    return True, "Password updated successfully."


def recent_month_slots(count=4):
    today = timezone.localdate()
    slots = []
    for offset in range(count - 1, -1, -1):
        month = today.month - offset
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        slots.append((year, month))
    return slots


def department_key(label):
    key = slugify(label or "").replace("-", "_")
    return key or "unassigned"


def get_admin_dashboard_context():
    total_students = User.objects.filter(role="student").count()
    new_students_this_week = User.objects.filter(
        role="student", created_at__gte=timezone.now() - timezone.timedelta(days=7)
    ).count()
    active_sanctions = Sanction.objects.filter(status="active").values("student").distinct().count()
    completed_sanctions = Sanction.objects.filter(status="completed").count()
    return {
        "total_students": total_students,
        "students_change": f"+{new_students_this_week} this week",
        "active_sanctions": active_sanctions,
        "sanctions_change": f"{active_sanctions} active record(s)",
        "completed_sanctions": completed_sanctions,
        "completed_period": "All time",
        "recent_activities": [],
    }


def serialize_sanction_for_admin(sanction):
    return {
        "id": sanction.id,
        "student_name": sanction.student_name,
        "student_id": sanction.student_id,
        "violation": sanction.violation,
        "required_hours": sanction.required_hours,
        "completed_hours": sanction.completed_hours,
        "status": sanction.status_label,
        "status_class": sanction.status_class,
        "date_issued": sanction.date_issued.isoformat(),
        "due_date": sanction.due_date.isoformat(),
        "progress_percent": sanction.progress_percent,
    }


def notify_student_of_sanction(request, sanction):
    """Email the student when a sanction is assigned."""
    if not sanction or not sanction.student or not sanction.student.email:
        return False
    login_url = request.build_absolute_uri(reverse("login"))
    subject = f"Sanction Tracker — New sanction assigned"
    department_label = sanction.department or "Unassigned"
    body = (
        f"Hello {sanction.student.display_name},\n\n"
        f"A new sanction has been added to your account.\n\n"
        f"Violation: {sanction.violation}\n"
        f"Department: {department_label}\n"
        f"Required hours: {sanction.required_hours}\n"
        f"Issued: {sanction.date_issued.isoformat()}\n"
        f"Due: {sanction.due_date.isoformat()}\n\n"
        f"Visit {login_url} to review the sanction and submit any required service-hour proof.\n\n"
        "If you believe this notice is a mistake, please contact student affairs."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@sanctiontracker.local")
    try:
        send_mail(subject, body, from_email, [sanction.student.email])
        return True
    except Exception:
        logger.exception("Failed to send sanction notification to %s", sanction.student.email)
        return False


@login_required
def sanction_management_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    sanction_types = list(SanctionType.objects.all())
    sanctions = [
        serialize_sanction_for_admin(sanction)
        for sanction in Sanction.objects.select_related("student", "sanction_type").all()
    ]
    students = [
        {
            "id": student.id,
            "name": student.display_name,
            "code": student.identifier,
            "department": student.department or "",
        }
        for student in User.objects.filter(role="student").order_by("first_name", "last_name", "username")
    ]
    selected_student_id = request.GET.get("student_id")
    selected_student = None
    if selected_student_id:
        try:
            student_id_int = int(selected_student_id)
        except (TypeError, ValueError):
            student_id_int = None
        if student_id_int is not None:
            selected_student = next((stud for stud in students if stud["id"] == student_id_int), None)

    context = {
        "sanctions": sanctions,
        "students": students,
        "current_date": timezone.localdate().isoformat(),
        "sanction_types": sanction_types,
        "selected_student": selected_student,
    }
    return render(request, "admin/sanction_management.html", context)


@login_required
def add_sanction_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            student_id = parse_non_negative_int(request.POST.get("student_id"), "Student")
            student = User.objects.get(id=student_id, role="student")
            sanction_type_description = (request.POST.get("violation") or "").strip()
            sanction_type = SanctionType.objects.filter(description__iexact=sanction_type_description).first()
            default_hours = sanction_type.hours if sanction_type else None
            required_hours = parse_non_negative_int(
                request.POST.get("required_hours"),
                "Required hours",
                default=default_hours,
            )
            if required_hours <= 0:
                raise ValueError("Required hours must be greater than zero.")

            date_issued = parse_iso_date(request.POST.get("date_issued"), "Date issued")
            due_date = parse_iso_date(request.POST.get("due_date"), "Due date")
            department = (request.POST.get("department") or "").strip()

            violation_text = sanction_type.description if sanction_type else sanction_type_description
            if not violation_text:
                raise ValueError("Violation is required.")

            sanction = Sanction.objects.create(
                student=student,
                sanction_type=sanction_type,
                violation_snapshot=violation_text,
                department=department,
                required_hours=required_hours,
                date_issued=date_issued,
                due_date=due_date,
            )
            email_sent = notify_student_of_sanction(request, sanction)
            status_note = (
                "An email notification was sent to the student."
                if email_sent
                else "Email notification could not be delivered; please inform the student manually."
            )
            messages.success(
                request,
                (
                    f"Sanction added successfully for {student.display_name} ({student.identifier}) due {due_date}. "
                    f"{status_note}"
                ),
            )
        except User.DoesNotExist:
            messages.error(request, "Selected student was not found.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("sanction_management")

    return redirect("sanction_management")


@login_required
def add_sanction_type_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            description = (request.POST.get("description") or "").strip()
            if not description:
                raise ValueError("Violation description is required.")
            if SanctionType.objects.filter(description__iexact=description).exists():
                raise ValueError("That sanction type already exists.")

            required_hours = parse_non_negative_int(request.POST.get("required_hours"), "Required hours")
            if required_hours <= 0:
                raise ValueError("Required hours must be greater than zero.")
            gravity = normalize_gravity(request.POST.get("gravity"))
            SanctionType.objects.create(description=description, hours=required_hours, gravity=gravity)
            messages.success(
                request,
                f'Sanction type "{description}" requiring {required_hours} hour(s) ({gravity}) added.',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("sanction_management")


@login_required
def edit_sanction_type_view(request, sanction_type_id):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            sanction_type = SanctionType.objects.get(id=sanction_type_id)
            description = (request.POST.get("description") or "").strip()
            if not description:
                raise ValueError("Violation description is required.")
            duplicate_exists = SanctionType.objects.exclude(id=sanction_type_id).filter(
                description__iexact=description
            ).exists()
            if duplicate_exists:
                raise ValueError("Another sanction type already uses that description.")

            required_hours = parse_non_negative_int(request.POST.get("required_hours"), "Required hours")
            if required_hours <= 0:
                raise ValueError("Required hours must be greater than zero.")

            sanction_type.description = description
            sanction_type.hours = required_hours
            sanction_type.gravity = normalize_gravity(request.POST.get("gravity"))
            sanction_type.save()
            messages.success(request, f'Sanction type "{description}" updated successfully.')
        except SanctionType.DoesNotExist:
            messages.error(request, "Sanction type not found.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("sanction_management")


@login_required
def delete_sanction_type_view(request, sanction_type_id):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            sanction_type = SanctionType.objects.get(id=sanction_type_id)
            description = sanction_type.description
            sanction_type.delete()
            messages.warning(request, f'Sanction type "{description}" removed successfully.')
        except SanctionType.DoesNotExist:
            messages.error(request, "Sanction type not found.")
    return redirect("sanction_management")


@login_required
def add_new_student_with_sanction_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            student_code = (request.POST.get("new_student_id") or "").strip()
            full_name = (request.POST.get("full_name") or "").strip()
            email = (request.POST.get("new_student_email") or "").strip()
            course_year = (request.POST.get("course_year") or "").strip()
            department = (request.POST.get("new_student_department") or "").strip()
            violation = (request.POST.get("new_violation") or "").strip()
            sanction_type = SanctionType.objects.filter(description__iexact=violation).first()
            default_hours = sanction_type.hours if sanction_type else None
            required_hours = parse_non_negative_int(
                request.POST.get("new_required_hours"),
                "Required hours",
                default=default_hours,
            )
            if required_hours <= 0:
                raise ValueError("Required hours must be greater than zero.")

            date_issued = parse_iso_date(request.POST.get("new_date_issued"), "Date issued")
            due_date = parse_iso_date(request.POST.get("new_due_date"), "Due date")
            if not full_name:
                raise ValueError("Student full name is required.")
            if not email:
                raise ValueError("Student email is required.")
            if not student_code:
                raise ValueError("Student ID is required.")
            if User.objects.filter(email__iexact=email).exists():
                raise ValueError("Email is already in use.")
            if User.objects.filter(student_code__iexact=student_code).exists() or User.objects.filter(username__iexact=student_code).exists():
                raise ValueError("Student ID is already in use.")

            first_name, last_name = split_full_name(full_name)
            username = student_code
            temp_password = student_code

            student = User.objects.create_user(
                username=username,
                email=email,
                password=temp_password,
                first_name=first_name,
                last_name=last_name,
                role="student",
                status="active",
                student_code=student_code or None,
                department=department,
                course_year=course_year,
            )

            Sanction.objects.create(
                student=student,
                sanction_type=sanction_type,
                violation_snapshot=violation or (sanction_type.description if sanction_type else "Unspecified"),
                department=department,
                required_hours=required_hours,
                date_issued=date_issued,
                due_date=due_date,
            )

            violation_label = violation or (sanction_type.description if sanction_type else "Unspecified")
            subject = "Sanction Tracker — Access details"
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@sanctiontracker.local")
            sanction_summary = (
                f"{violation_label} · Required hours: {required_hours} · "
                f"Issued: {date_issued.isoformat()} · Due: {due_date.isoformat()}"
            )
            login_url = request.build_absolute_uri(reverse("login"))
            body = (
                f"Hello {student.display_name},\n\n"
                f"Welcome! An administrator created your account in the Sanction Tracker system.\n"
                f"Username: {username}\n"
                f"Password: {temp_password}\n\n"
                f"This is a reminder that you currently have a sanction assigned:\n"
                f"{sanction_summary}\n\n"
                f"Please log in at {request.build_absolute_uri('/')[:-1]}login/ to view your sanctions "
                f"and submit proof of hours once completed.\n\n"
                "If you did not expect this message, please contact your dean's office."
            )
            try:
                send_mail(subject, body, from_email, [student.email])
                email_note = "The credentials were emailed to the student."
            except Exception as exc:
                logger.exception("Failed to send sanction welcome email to %s", student.email)
                email_note = "Email delivery failed; please notify the student manually."

            messages.success(
                request,
                (
                    f"New student {student.display_name} created and sanctioned successfully. "
                    f"Username: {student.username} | Temporary password: {temp_password}. "
                    f"{email_note}"
                ),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("sanction_management")

    return redirect("sanction_management")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            if has_admin_access(user):
                messages.success(request, "Welcome, admin!")
                return redirect("admin_dashboard")
            if getattr(user, "is_student", False):
                messages.success(request, f"Welcome back, {user.display_name}!")
                return redirect("student_dashboard")
            messages.error(request, "Your account is not authorized to use this system.")
            logout(request)
            return redirect("login")
        messages.error(request, "Invalid username or password.")

    return render(request, "auth/login.html")


@login_required
def dashboard_view(request):
    if has_admin_access(request.user):
        return redirect("admin_dashboard")
    messages.error(request, "You do not have permission to access this page.")
    logout(request)
    return redirect("login")


@login_required
def admin_dashboard_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")
    return render(request, "admin/admin_dashboard.html", get_admin_dashboard_context())


@login_required
def student_management_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    students = User.objects.filter(role="student")

    search_query = request.GET.get("search", "").strip()
    if search_query:
        student_filters = (
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(student_code__icontains=search_query)
            | Q(department__icontains=search_query)
            | Q(course_year__icontains=search_query)
        )
        if search_query.isdigit():
            student_filters |= Q(id=int(search_query))
        students = students.filter(student_filters).distinct()

    context = {
        "students": students,
        "search_query": search_query,
        "student_count": students.count(),
    }

    return render(request, "admin/student_management.html", context)


@login_required
def student_detail_view(request, student_id):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    try:
        student = User.objects.get(id=student_id, role="student")
    except User.DoesNotExist:
        messages.error(request, "Student not found.")
        return redirect("student_management")
    sanctions_qs = (
        Sanction.objects.filter(student=student)
        .select_related("sanction_type")
        .order_by("-date_issued", "-created_at")
    )
    today = timezone.localdate()
    overdue_count = 0
    sanctions = []
    for sanction in sanctions_qs:
        overdue = sanction.status == "active" and sanction.due_date < today
        if overdue:
            overdue_count += 1
        sanctions.append(
            {
                "id": sanction.id,
                "violation": sanction.violation,
                "required_hours": sanction.required_hours,
                "completed_hours": sanction.completed_hours,
                "status_label": sanction.status_label,
                "status": sanction.status,
                "date_issued": sanction.date_issued,
                "due_date": sanction.due_date,
                "overdue": overdue,
            }
        )

    has_active = sanctions_qs.filter(status="active").exists()
    context = {
        "student": student,
        "sanctions": sanctions,
        "overdue_count": overdue_count,
        "sanction_status": "With Sanction" if has_active else "Cleared",
    }
    return render(request, "admin/student_detail.html", context)


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")


@login_required
def edit_sanction_view(request, sanction_id):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            sanction = Sanction.objects.get(id=sanction_id)
            completed_hours_input = request.POST.get("completed_hours")
            due_date_input = request.POST.get("due_date")
            status_input = (request.POST.get("status") or "").strip().lower()

            if completed_hours_input not in (None, ""):
                sanction.completed_hours = parse_non_negative_int(completed_hours_input, "Completed hours")
            if due_date_input:
                sanction.due_date = parse_iso_date(due_date_input, "Due date")
            if status_input in {"active", "completed"}:
                sanction.status = status_input

            sanction.save()
            messages.success(request, f"Sanction {sanction_id} updated successfully.")
        except Sanction.DoesNotExist:
            messages.error(request, "Sanction not found.")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("sanction_management")


@login_required
def delete_sanction_view(request, sanction_id):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        try:
            sanction = Sanction.objects.get(id=sanction_id)
            sanction.delete()
            messages.success(request, f"Sanction {sanction_id} deleted successfully.")
        except Sanction.DoesNotExist:
            messages.error(request, "Sanction not found.")
    return redirect("sanction_management")


@login_required
def service_hours_management_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    pending_qs = ServiceHourSubmission.objects.filter(status="pending").select_related("student")
    approved_qs = ServiceHourSubmission.objects.filter(status="approved").select_related("student", "reviewed_by")
    rejected_qs = ServiceHourSubmission.objects.filter(status="rejected")

    pending_submissions = pending_qs.count()
    approved_submissions = approved_qs.count()
    rejected_submissions = rejected_qs.count()
    active_students = (
        ServiceHourSubmission.objects.filter(status="pending").values("student").distinct().count()
    )
    pending_hours = pending_qs.aggregate(total=Sum("hours"))["total"] or Decimal("0")
    approved_hours = approved_qs.aggregate(total=Sum("hours"))["total"] or Decimal("0")
    total_reviewed = approved_submissions + rejected_submissions
    completion_rate = int((approved_submissions / total_reviewed) * 100) if total_reviewed else 0

    pending_submissions_list = [
        {
            "id": submission.id,
            "student_name": submission.student.display_name,
            "student_id": submission.student.identifier,
            "date": submission.date.isoformat(),
            "hours": format_hours(submission.hours),
            "description": submission.description,
            "status": submission.status,
            "proof_url": submission.proof.url if submission.proof else "",
        }
        for submission in pending_qs.order_by("-date", "-created_at")
    ]
    recently_validated_list = [
        {
            "student_name": submission.student.display_name,
            "student_id": submission.student.identifier,
            "date": submission.date.isoformat(),
            "hours": format_hours(submission.hours),
            "status_label": submission.get_status_display(),
            "reviewed_by": submission.reviewed_by.display_name if submission.reviewed_by else "System",
            "proof_url": submission.proof.url if submission.proof else "",
        }
        for submission in approved_qs.order_by("-reviewed_at", "-updated_at", "-date")[:10]
    ]

    context = {
        "pending_submission_count": pending_submissions,
        "approved_submission_count": approved_submissions,
        "active_student_submission_count": active_students,
        "pending_hours_total": format_hours(pending_hours),
        "approved_hours_total": format_hours(approved_hours),
        "completion_rate": completion_rate,
        "pending_submissions": pending_submissions_list,
        "recently_validated_submissions": recently_validated_list,
    }
    return render(request, "admin/servicehours_management.html", context)


@login_required
def update_service_submission_status(request, submission_id):
    if not has_admin_access(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    status = (request.POST.get("status") or "").strip().lower()
    if status not in {"approved", "rejected"}:
        return JsonResponse({"error": "Invalid status"}, status=400)

    try:
        submission = ServiceHourSubmission.objects.get(id=submission_id)
    except ServiceHourSubmission.DoesNotExist:
        return JsonResponse({"error": "Submission not found"}, status=404)

    submission.status = status
    submission.reviewed_by = request.user
    submission.reviewed_at = timezone.now()
    submission.save()
    return JsonResponse({"success": True, "status": submission.get_status_display()})


@login_required
def update_concern_status(request, concern_id):
    if not has_admin_access(request.user):
        return JsonResponse({"error": "Unauthorized"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    status = (request.POST.get("status") or "").strip().lower()
    valid_statuses = {"new", "progress", "resolved"}
    if status not in valid_statuses:
        return JsonResponse({"error": "Invalid status"}, status=400)

    try:
        concern = Concern.objects.get(id=concern_id)
    except Concern.DoesNotExist:
        return JsonResponse({"error": "Concern not found"}, status=404)

    concern.status = status
    concern.save()
    return JsonResponse(
        {
            "success": True,
            "status_label": concern.get_status_display(),
            "status_class": concern.status_class,
        }
    )


@login_required
def concerns_management_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    concerns = [
        {
            "id": concern.id,
            "student_name": concern.student.display_name,
            "student_id": concern.student.identifier,
            "subject": concern.subject,
            "date_submitted": concern.created_at.date().isoformat(),
            "status_label": concern.status_label,
            "status_class": concern.status_class,
            "message": concern.message,
        }
        for concern in Concern.objects.select_related("student").all()
    ]

    context = {
        "concerns": concerns,
    }
    return render(request, "admin/concerns_management.html", context)


@login_required
def student_dashboard_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    sanctions_qs = Sanction.objects.filter(student=request.user)
    submissions_qs = ServiceHourSubmission.objects.filter(student=request.user)

    required_hours_total = sanctions_qs.aggregate(total=Sum("required_hours"))["total"] or 0
    approved_hours_total = submissions_qs.filter(status="approved").aggregate(total=Sum("hours"))["total"] or Decimal(
        "0"
    )
    remaining_hours = max(Decimal(required_hours_total) - approved_hours_total, Decimal("0"))
    progress_percentage = (
        int((approved_hours_total / Decimal(required_hours_total)) * 100) if required_hours_total else 0
    )

    overview_cards = [
        {
            "label": "Active Sanctions",
            "value": sanctions_qs.filter(status="active").count(),
            "meta": "Currently active",
            "icon": "gavel",
            "color": "#d55ac8",
        },
        {
            "label": "Required Hours",
            "value": required_hours_total,
            "meta": "Total for all sanctions",
            "icon": "hourglass_full",
            "color": "#5b36ff",
        },
        {
            "label": "Completed Hours",
            "value": format_hours(approved_hours_total),
            "meta": f"{progress_percentage}% complete",
            "icon": "check_circle",
            "color": "#ec4899",
        },
        {
            "label": "Remaining Hours",
            "value": format_hours(remaining_hours),
            "meta": "Hours still needed",
            "icon": "schedule",
            "color": "#d946ef",
        },
    ]

    month_totals = {}
    for submission in submissions_qs.filter(status="approved"):
        key = (submission.date.year, submission.date.month)
        month_totals[key] = month_totals.get(key, Decimal("0")) + submission.hours

    monthly_hours = []
    for year, month in recent_month_slots(4):
        hours = month_totals.get((year, month), Decimal("0"))
        month_label = datetime(year, month, 1).strftime("%b")
        monthly_hours.append({"month": month_label, "hours": format_hours(hours)})

    max_hours = max((float(entry["hours"]) for entry in monthly_hours), default=0.0)
    for entry in monthly_hours:
        value = float(entry["hours"])
        entry["percentage"] = int((value / max_hours) * 100) if max_hours else 0

    activity_feed = []
    combined_events = []
    for sanction in sanctions_qs.order_by("-created_at")[:5]:
        combined_events.append(
            {
                "created_at": sanction.created_at,
                "title": f'New sanction assigned: "{sanction.violation}".',
                "icon": "report",
                "color": "#ef4444",
            }
        )
    for submission in submissions_qs.order_by("-created_at")[:5]:
        if submission.status == "approved":
            title = f'{format_hours(submission.hours)} hour(s) for "{submission.description}" were approved.'
            icon = "verified"
            color = "#10b981"
        elif submission.status == "rejected":
            title = f'Submission for "{submission.description}" was rejected.'
            icon = "error"
            color = "#ef4444"
        else:
            title = f'Submitted {format_hours(submission.hours)} hour(s) for "{submission.description}".'
            icon = "volunteer_activism"
            color = "#a855f7"

        combined_events.append(
            {
                "created_at": submission.created_at,
                "title": title,
                "icon": icon,
                "color": color,
            }
        )

    for event in sorted(combined_events, key=lambda item: item["created_at"], reverse=True)[:5]:
        activity_feed.append(
            {
                "title": event["title"],
                "time": format_activity_time(event["created_at"]),
                "icon": event["icon"],
                "color": event["color"],
            }
        )

    context = {
        "student_name": request.user.display_name,
        "overview_cards": overview_cards,
        "monthly_hours": monthly_hours,
        "activity_feed": activity_feed,
        "active_section": "dashboard",
    }
    return render(request, "Student/dashboard.html", context)


@login_required
def student_sanctions_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    sanctions = []
    for sanction in Sanction.objects.filter(student=request.user):
        sanctions.append(
            {
                "id": sanction.id,
                "title": sanction.violation,
                "issued": sanction.date_issued.isoformat(),
                "status_label": sanction.status_label,
                "completed_hours": sanction.completed_hours,
                "required_hours": sanction.required_hours,
                "note": sanction.note,
                "progress_percentage": sanction.progress_percent,
                "status_class": "status-completed" if sanction.status == "completed" else "status-active",
            }
        )

    context = {
        "student_name": request.user.display_name,
        "sanctions": sanctions,
        "active_section": "sanctions",
    }
    return render(request, "Student/sanctions.html", context)


@login_required
def student_service_hours_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    if request.method == "POST":
        try:
            sanction_id = request.POST.get("sanction")
            sanction = None
            if sanction_id:
                try:
                    sanction = Sanction.objects.get(id=int(sanction_id), student=request.user)
                except (Sanction.DoesNotExist, ValueError):
                    raise ValueError("Selected sanction is invalid.")
            if not sanction:
                raise ValueError("Please select a valid sanction.")

            submission_date = parse_iso_date(request.POST.get("date"), "Date")
            hours = parse_decimal(request.POST.get("hours"), "Hours")
            description = (request.POST.get("description") or "").strip()
            if not description:
                raise ValueError("Description is required.")
            proof_file = request.FILES.get("proof")

            ServiceHourSubmission.objects.create(
                student=request.user,
                sanction=sanction,
                date=submission_date,
                hours=hours,
                description=description,
                proof=proof_file,
            )
            messages.success(request, "Service hours submitted successfully. Awaiting validation.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("student_service_hours")

    sanctions_qs = Sanction.objects.filter(student=request.user)
    submissions_qs = ServiceHourSubmission.objects.filter(student=request.user)

    required_hours_total = sanctions_qs.aggregate(total=Sum("required_hours"))["total"] or 0
    completed_hours_total = submissions_qs.filter(status="approved").aggregate(total=Sum("hours"))["total"] or Decimal(
        "0"
    )
    remaining_hours = max(Decimal(required_hours_total) - completed_hours_total, Decimal("0"))
    progress_percentage = (
        int((completed_hours_total / Decimal(required_hours_total)) * 100) if required_hours_total else 0
    )

    submissions = [
        {
            "id": entry.id,
            "date": entry.date.strftime("%m/%d/%Y"),
            "hours": format_hours(entry.hours),
            "description": entry.description,
            "status": entry.get_status_display(),
            "status_class": entry.status_class,
            "proof_url": entry.proof.url if entry.proof else "",
        }
        for entry in submissions_qs
    ]

    sanction_options = [{"id": sanction.id, "title": sanction.violation} for sanction in sanctions_qs]

    context = {
        "student_name": request.user.display_name,
        "required_hours": required_hours_total,
        "completed_hours": format_hours(completed_hours_total),
        "remaining_hours": format_hours(remaining_hours),
        "progress_percentage": progress_percentage,
        "submissions": submissions,
        "sanction_options": sanction_options,
        "active_section": "servicehours",
    }
    return render(request, "Student/service_hours.html", context)


@login_required
def student_records_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    sanctions = [
        {
            "violation": sanction.violation,
            "issued": sanction.date_issued.isoformat(),
            "hours_required": sanction.required_hours,
            "status_label": sanction.status_label,
            "status_class": "status-completed" if sanction.status == "completed" else "status-active",
        }
        for sanction in Sanction.objects.filter(student=request.user)
    ]

    community_hours = [
        {
            "date": entry.date.isoformat(),
            "hours": format_hours(entry.hours),
            "description": entry.description,
        }
        for entry in ServiceHourSubmission.objects.filter(student=request.user, status="approved")
    ]

    context = {
        "student_name": request.user.display_name,
        "sanctions": sanctions,
        "community_hours": community_hours,
        "active_section": "records",
    }
    return render(request, "Student/records.html", context)


@login_required
def student_help_center_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    valid_topics = {value for value, _ in Concern.TOPIC_CHOICES}
    if request.method == "POST":
        if request.POST.get("form_type") == "password":
            current_password = request.POST.get("current_password") or ""
            new_password = request.POST.get("new_password") or ""
            confirm_password = request.POST.get("confirm_password") or ""
            success, update_message = attempt_student_password_change(
                request, current_password, new_password, confirm_password
            )
            if success:
                messages.success(request, update_message)
            else:
                messages.error(request, update_message)
            return redirect("student_help_center")

        subject = (request.POST.get("subject") or "").strip()
        message_text = (request.POST.get("message") or "").strip()
        if subject not in valid_topics:
            messages.error(request, "Please select a valid concern topic.")
            return redirect("student_help_center")
        if not message_text:
            messages.error(request, "Please provide a detailed description of your concern.")
            return redirect("student_help_center")

        Concern.objects.create(
            student=request.user,
            subject=subject,
            message=message_text,
            status="new",
        )
        messages.success(request, "Concern submitted successfully. An admin will review it shortly.")
        return redirect("student_help_center")

    concern_topics = [label for _, label in Concern.TOPIC_CHOICES]
    context = {
        "student_name": request.user.display_name,
        "concern_topics": concern_topics,
        "active_section": "help",
    }
    return render(request, "Student/help_center.html", context)


@login_required
def student_settings_view(request):
    if not request.user.is_student:
        messages.error(request, "Please log in with a student account to view the student portal.")
        return redirect("admin_dashboard" if has_admin_access(request.user) else "login")

    if request.method == "POST":
        current_password = request.POST.get("current_password") or ""
        new_password = request.POST.get("new_password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        success, message_text = attempt_student_password_change(
            request, current_password, new_password, confirm_password
        )
        if success:
            messages.success(request, message_text)
        else:
            messages.error(request, message_text)
        return redirect("student_settings")

    context = {
        "student_name": request.user.display_name,
        "active_section": "settings",
    }
    return render(request, "Student/settings.html", context)


@login_required
def reports_management_view(request):
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    month_slots = recent_month_slots(6)
    month_labels = [datetime(year, month, 1).strftime("%b") for year, month in month_slots]

    student_departments = set(
        User.objects.filter(role="student").exclude(department="").values_list("department", flat=True)
    )
    sanction_departments = set(Sanction.objects.exclude(department="").values_list("department", flat=True))
    department_labels = sorted(student_departments | sanction_departments)

    include_unassigned = (
        User.objects.filter(role="student").filter(Q(department="") | Q(department__isnull=True)).exists()
        or Sanction.objects.filter(Q(department="") | Q(department__isnull=True)).exists()
    )
    if include_unassigned:
        department_labels.append("Unassigned")

    department_options = [{"key": "all", "label": "All Departments"}]
    used_keys = {"all"}
    for label in department_labels:
        base_key = department_key(label)
        key = base_key
        counter = 2
        while key in used_keys:
            key = f"{base_key}_{counter}"
            counter += 1
        used_keys.add(key)
        department_options.append({"key": key, "label": label})

    def scoped_data(label):
        students = User.objects.filter(role="student")
        sanctions = Sanction.objects.all()
        approved_submissions = ServiceHourSubmission.objects.filter(status="approved")

        if label is None:
            return students, sanctions, approved_submissions
        if label == "Unassigned":
            students = students.filter(Q(department="") | Q(department__isnull=True))
            sanctions = sanctions.filter(
                Q(department="")
                | Q(department__isnull=True)
                | Q(student__department="")
                | Q(student__department__isnull=True)
            ).distinct()
            approved_submissions = approved_submissions.filter(
                Q(student__department="") | Q(student__department__isnull=True)
            )
            return students, sanctions, approved_submissions

        students = students.filter(department=label)
        sanctions = sanctions.filter(Q(department=label) | Q(student__department=label)).distinct()
        approved_submissions = approved_submissions.filter(student__department=label)
        return students, sanctions, approved_submissions

    def build_report_config(label):
        students_qs, sanctions_qs, approved_qs = scoped_data(label)
        monthly_values = [
            sanctions_qs.filter(date_issued__year=year, date_issued__month=month).count()
            for year, month in month_slots
        ]

        top_students_raw = (
            students_qs.annotate(
                total_hours=Sum("service_submissions__hours", filter=Q(service_submissions__status="approved"))
            )
            .order_by("-total_hours", "first_name", "username")[:5]
        )
        top_students = [
            {"name": student.display_name, "hours": format_hours(student.total_hours)}
            for student in top_students_raw
            if student.total_hours
        ]

        required_total = sanctions_qs.aggregate(total=Sum("required_hours"))["total"] or 0
        completed_total = approved_qs.aggregate(total=Sum("hours"))["total"] or Decimal("0")
        remaining_total = max(Decimal(required_total) - completed_total, Decimal("0"))
        completion = int((completed_total / Decimal(required_total)) * 100) if required_total else 0

        label_text = "All Departments" if label is None else label
        if label is None:
            dean_email = "dean.office@school.edu"
        else:
            email_slug = slugify(label_text).replace("-", ".")
            dean_email = f"dean.{email_slug or 'department'}@school.edu"

        return {
            "label": label_text,
            "months": monthly_values,
            "topStudents": top_students,
            "summary": {
                "required": required_total,
                "completed": format_hours(completed_total),
                "remaining": format_hours(remaining_total),
                "completion": completion,
            },
            "deanEmail": dean_email,
        }

    reports_data = {"all": build_report_config(None)}
    for option in department_options:
        if option["key"] == "all":
            continue
        reports_data[option["key"]] = build_report_config(option["label"])

    report_concerns = [
        {
            "student_name": concern.student.display_name,
            "subject": concern.subject,
            "date_submitted": concern.created_at.date().isoformat(),
            "status_class": concern.status_class,
            "status_label": concern.status_label,
        }
        for concern in Concern.objects.select_related("student").all()[:10]
    ]

    context = {
        "department_options": department_options,
        "reports_data": reports_data,
        "report_month_labels": month_labels,
        "report_concerns": report_concerns,
    }
    return render(request, "admin/reports_management.html", context)


@login_required
def create_student_view(request):
    """Create a new student account"""
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")

        if password != password_confirm:
            messages.error(request, "Passwords do not match.")
            return redirect("create_student")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("create_student")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect("create_student")

        try:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role="student",
                status="active",
            )
            messages.success(request, f"Student {username} created successfully!")
            return redirect("student_management")
        except Exception as exc:
            messages.error(request, f"Error creating student: {str(exc)}")

    messages.info(request, "Use Student Management to view and manage students.")
    return redirect("student_management")


@login_required
def create_admin_view(request):
    """Create a new admin account"""
    if not has_admin_access(request.user):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")

        if password != password_confirm:
            messages.error(request, "Passwords do not match.")
            return redirect("create_admin")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("create_admin")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect("create_admin")

        try:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role="admin",
                status="active",
                is_staff=True,
            )
            messages.success(request, f"Admin {username} created successfully!")
            return redirect("student_management")
        except Exception as exc:
            messages.error(request, f"Error creating admin: {str(exc)}")

    messages.info(request, "Use Django Admin to create additional admins.")
    return redirect("/admin/")
