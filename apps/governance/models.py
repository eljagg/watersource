"""Milestone acceptance log (v0.13.0, stakeholder model package 4; doc 17 §package 4).

The contract's payment milestones (bid M1–M9) and the Work Plan adoption
milestone are recorded here. The ICT Manager, as approver of record, marks a
milestone **accepted** on the Steering Committee's behalf or **returns** it
with remarks; every decision is written to the audit trail.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class MilestoneStatus(models.TextChoices):
    """Where a milestone stands."""

    PLANNED = "planned", "Planned"
    DELIVERED = "delivered", "Delivered — awaiting acceptance"
    ACCEPTED = "accepted", "Accepted"
    RETURNED = "returned", "Returned for rework"


class Milestone(TimeStampedModel):
    """One contract milestone and its acceptance record."""

    number = models.PositiveSmallIntegerField(unique=True)
    code = models.CharField(max_length=8, unique=True, help_text="M1 … M9 as in the bid; M17 for adoption sign-off.")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    due_week = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Contract week from commencement.")
    due_date = models.DateField(null=True, blank=True, help_text="Set once the commencement date is fixed.")
    payment_pct = models.DecimalField("Payment %", max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=MilestoneStatus.choices, default=MilestoneStatus.PLANNED, db_index=True)
    delivered_on = models.DateField(null=True, blank=True)
    evidence_url = models.URLField(blank=True, help_text="Where the deliverable or report lives (optional).")
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="milestone_decisions")
    remarks = models.TextField(blank=True, help_text="The approver's remarks on acceptance or return.")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.code} {self.title}"

    @property
    def is_overdue(self) -> bool:
        """Past its due date without acceptance."""
        return bool(self.due_date) and self.status != MilestoneStatus.ACCEPTED and self.due_date < timezone.localdate()

    def decide(self, user, accepted: bool, remarks: str = ""):
        """Record acceptance or return by the approver of record, audited."""
        from apps.core.audit import log

        self.status = MilestoneStatus.ACCEPTED if accepted else MilestoneStatus.RETURNED
        self.decided_at = timezone.now()
        self.decided_by = user
        self.remarks = remarks
        if accepted and not self.delivered_on:
            self.delivered_on = timezone.localdate()
        self.save()
        log("milestone.accepted" if accepted else "milestone.returned", target=self, actor=user, summary=f"{self.code} {self.title}", remarks=remarks)
        return self

    def mark_delivered(self, user, on=None, evidence_url: str = ""):
        """The contractor (or administrator) records delivery, ready for the approver."""
        from apps.core.audit import log

        self.status = MilestoneStatus.DELIVERED
        self.delivered_on = on or timezone.localdate()
        if evidence_url:
            self.evidence_url = evidence_url
        self.save()
        log("milestone.delivered", target=self, actor=user, summary=f"{self.code} {self.title}")
        return self


#: the bid's payment milestones (weeks from commencement) and the Work Plan adoption milestone. Titles follow the development stages in
#: design doc 12 and are editable in the admin console once the contract schedule is confirmed.
DEFAULT_MILESTONES = [
    (1, "M1", 5, "Inception report and agreed work plan", "Initiation complete: kick-off, governance, work plan and communication plan agreed with the Steering Committee."),
    (2, "M2", 9, "Requirements and design sign-off", "Confirmed requirements, data model, category framework and technical design (design docs 12–14)."),
    (3, "M3", 18, "Foundation and database delivered",
     "Accounts, roles, security, workflow engine, category framework, fourteen observation tables; data-quality assessment report."),
    (4, "M4", 20, "Licence Application Processing module", "Licence applications, review stages, technical assessment, licence issue and register, WMU balance."),
    (5, "M5", 24, "Data Submission module", "Form, CSV and API submission, validation, anomaly flags, promotion into the observation tables, open data."),
    (6, "M6", 27, "Integrations and API", "Aquarius, HGA and DSpace adapters, REST API v1, GIS desk and map, exports."),
    (7, "M7", 30, "Business intelligence and hardening", "Dashboards and wall display, performance test, security hardening, VAPT findings closed."),
    (8, "M8", 34, "Data migration and UAT", "Legacy data migrated, cleansing queue cleared, user-acceptance testing signed by each unit's Super User."),
    (9, "M9", 36, "Training, go-live and handover",
     "Training delivered, production go-live on the WRA server, manuals and source code handed over; defects-liability period begins."),
    (17, "M17", 36, "Adoption sign-off by every unit", "Each unit's Super User confirms the unit is using the system (Work Plan M17; recorded in the unit console)."),
]
