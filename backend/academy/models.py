"""Persistent academy records. Authorization is enforced in views and the owner-only admin."""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError

# Email uniqueness is case-insensitive; verification is separate from membership approval.
class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='email_case_insensitive_unique')]

# Only explicitly assigned coaches may access the squad’s private training records.
class Squad(models.Model):
    name = models.CharField(max_length=80, unique=True)
    coaches = models.ManyToManyField(User, blank=True, related_name='coached_squads')
    def __str__(self): return self.name

# Directory numbers identify records, not shirt numbers. Accounts are linked after owner review.
class Player(models.Model):
    directory_number = models.PositiveIntegerField(unique=True)
    display_name = models.CharField(max_length=100)
    positions = models.CharField(max_length=240)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='player')
    squad = models.ForeignKey(Squad, null=True, blank=True, on_delete=models.SET_NULL)
    active = models.BooleanField(default=True)
    def __str__(self): return f'{self.directory_number}. {self.display_name}'

# Keep contact and emergency details private; optional media consent is independent of participation.
class Application(models.Model):
    STATUS = [('pending','Pending review'), ('approved','Approved'), ('correction','Correction requested'), ('declined','Declined')]
    KIND = [('student','Student'), ('graduate','Graduate'), ('adult','Other adult')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='application')
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30)
    date_of_birth = models.DateField()
    kind = models.CharField(max_length=10, choices=KIND)
    institution = models.CharField(max_length=180, blank=True)
    faculty = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    course = models.CharField(max_length=120, blank=True)
    level = models.CharField(max_length=40, blank=True)
    qualification = models.CharField(max_length=120, blank=True)
    graduation_year = models.PositiveIntegerField(null=True, blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    preferred_position = models.CharField(max_length=100)
    alternative_positions = models.CharField(max_length=180, blank=True)
    emergency_name = models.CharField(max_length=120)
    emergency_relationship = models.CharField(max_length=60)
    emergency_phone = models.CharField(max_length=30)
    rules_accepted = models.BooleanField(default=False)
    privacy_accepted = models.BooleanField(default=False)
    media_consent = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=20, default='2026-10-v1')
    status = models.CharField(max_length=12, choices=STATUS, default='pending')
    review_note = models.CharField(max_length=500, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.full_name

# Unconfirmed venues remain visibly marked until the coordinator confirms them.
class TrainingSession(models.Model):
    STATUS = [('scheduled','Scheduled'),('completed','Completed'),('postponed','Postponed'),('cancelled','Cancelled')]
    title = models.CharField(max_length=140)
    squad = models.ForeignKey(Squad, on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    venue = models.CharField(max_length=200)
    venue_confirmed = models.BooleanField(default=False)
    instructions = models.TextField(blank=True, max_length=3000)
    status = models.CharField(max_length=12, choices=STATUS, default='scheduled')
    def __str__(self): return f'{self.title} — {self.starts_at:%d %b %Y}'

# A player’s intention to attend; never treat this as actual attendance.
class Availability(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE)
    response = models.CharField(max_length=10, choices=[('yes','Attending'),('no','Unavailable'),('unsure','Not sure yet')])
    private_note = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['player','session'], name='one_availability_per_session')]

# One actual attendance record per player/session, written by authorized staff.
class Attendance(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=[('present','Present'),('late','Late'),('absent','Absent'),('excused','Excused')])
    recorded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['player','session'], name='one_attendance_per_session')]
    def clean(self):
        if self.player_id and self.session_id and self.player.squad_id != self.session.squad_id:
            raise ValidationError('Player and session must belong to the same squad.')

# Players see only their own shared feedback; staff-only notes stay private.
class Feedback(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    goal = models.CharField(max_length=200)
    message = models.TextField(max_length=3000)
    shared_with_player = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

# A blank squad targets approved members generally, not anonymous website visitors.
class Announcement(models.Model):
    title = models.CharField(max_length=180)
    body = models.TextField(max_length=5000)
    squad = models.ForeignKey(Squad, null=True, blank=True, on_delete=models.CASCADE, help_text='Blank means all approved members.')
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

# Store action and record identifiers, avoiding copies of sensitive profile values.
class AuditEvent(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    object_reference = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

# Hashed fixed-window counters limit account attempts; expired rows need scheduled cleanup.
class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()


class OwnerRecoveryCode(models.Model):
    """High-entropy recovery codes are stored only as SHA-256 digests."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OwnerSMSChallenge(models.Model):
    """One pending owner challenge; codes and browser bindings are never plaintext."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, blank=True)
    binding = models.CharField(max_length=64, blank=True)
    nonce = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    window_at = models.DateTimeField(null=True)
    sends = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    accepted = models.BooleanField(default=False)
