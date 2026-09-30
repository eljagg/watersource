"""``manage.py seed_demo_data`` — twelve months of synthetic data for demos, dashboards and browser tests.

Everything created here is prefixed ``DEMO`` (well/station names, party
names, ``demo.*`` user emails) so it can be wiped with ``--wipe`` and can never
be confused with migrated WRA data. Values are deterministic (fixed random
seed) so screenshots and tests are repeatable.

What it creates:

* six users, one per role, password from ``DEMO_PASSWORD`` (default
  ``WaterSource-Demo-2026!``) — ``demo.client``, ``demo.reviewer``,
  ``demo.approver``, ``demo.hydrologist``, ``demo.technician``, ``demo.admin``
* 12 wells, 4 streamflow stations, 2 springs, with lithology, casing, pump
  tests, status events, instruments, reference points and visits
* 40 licence applications over the last 12 months in every status, 25
  licences (some expiring soon, two expired)
* weekly well levels, daily station readings, monthly abstraction (a few
  over-limit), quarterly water-quality samples — graded and mostly approved,
  with the last month left "working"

On Railway set the variable ``DEMO_DATA=1`` and redeploy; the pre-deploy
migrate step runs this command. Refuses to run against a database that
already holds non-demo wells unless ``--force`` is given.
"""
from __future__ import annotations

import math
import os
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts import roles
from apps.accounts.models import User, UserType
from apps.core.models import ApprovalState, Classification, DataSource, ObservationGrade
from apps.lic.models import ApplicationStatus, Licence, LicenceApplication, LicenceStatus, Sequence, WaterSource
from apps.obs.models import AbstractionRecord, AbstractionSource, ApprovalPeriod, SampleSource, SeriesKind, StationReading, WaterQualitySample, WellState, WellWaterLevel
from apps.ref.models import (
    WMU,
    Basin,
    HydrostratUnit,
    Instrument,
    InstrumentInstallation,
    InstrumentKind,
    Parish,
    Party,
    PartyKind,
    ReferencePoint,
    River,
    SiteVisit,
    Spring,
    StreamflowStation,
    VisitPurpose,
    Well,
    WellCasing,
    WellEvent,
    WellLithology,
    WellPumpTest,
    WellStatusEvent,
    WellUse,
)

PREFIX = "DEMO"
DEMO_USERS = [
    ("demo.client@example.com", "Demo Client", UserType.CLIENT, roles.CLIENT),
    ("demo.reviewer@wra-demo.local", "Demo Reviewer", UserType.STAFF, roles.REVIEWER),
    ("demo.approver@wra-demo.local", "Demo Approver", UserType.STAFF, roles.APPROVER),
    ("demo.hydrologist@wra-demo.local", "Demo Hydrologist", UserType.STAFF, roles.HYDROLOGIST),
    ("demo.technician@wra-demo.local", "Demo Technician", UserType.STAFF, roles.TECHNICIAN),
    ("demo.admin@wra-demo.local", "Demo Administrator", UserType.STAFF, roles.ADMINISTRATOR),
]
WELLS = [  # name, parish code, basin code, wmu code, use, easting, northing
    ("Bog Walk 1", "STC", "B03", "W05", WellUse.PUBLIC_SUPPLY, 758200, 653100),
    ("Innswood 3", "STC", "B03", "W05", WellUse.AGRICULTURAL, 752900, 646300),
    ("Bernard Lodge 7", "STC", "B03", "W05", WellUse.AGRICULTURAL, 757400, 640900),
    ("Old Harbour 2", "STC", "B03", "W05", WellUse.INDUSTRIAL, 741800, 641200),
    ("May Pen 5", "CLA", "B04", "W06", WellUse.PUBLIC_SUPPLY, 723600, 645800),
    ("Vere 12", "CLA", "B04", "W06", WellUse.AGRICULTURAL, 716500, 631900),
    ("Milk River 1", "CLA", "B04", "W07", WellUse.OBSERVATION, 711200, 629400),
    ("Lacovia 4", "STE", "B05", "W08", WellUse.AGRICULTURAL, 668900, 637200),
    ("Elim 2", "STE", "B05", "W08", WellUse.OBSERVATION, 664300, 646100),
    ("Cornwall 9", "STJ", "B07", "W11", WellUse.PUBLIC_SUPPLY, 660100, 683200),
    ("Falmouth 6", "TRE", "B08", "W12", WellUse.PRIVATE, 686400, 686900),
    ("Yallahs 3", "STT", "B01", "W03", WellUse.PUBLIC_SUPPLY, 807900, 645300),
]
STATIONS = [  # name, river code, parish, basin, wmu, easting, northing
    ("Rio Cobre at Bog Walk", "RCB", "STC", "B03", "W05", 757100, 654200),
    ("Rio Minho at Danks", "RMN", "CLA", "B04", "W06", 722900, 650800),
    ("Black River at Lacovia", "BLK", "STE", "B05", "W08", 667200, 636100),
    ("Hope River at Gordon Town", "HOP", "STA", "B02", "W04", 786500, 655300),
]
SPRINGS = [("Roaring River Spring", "STE"), ("Fontabelle Spring", "STC")]
LITHOLOGY = [("Topsoil and clay", 0, 4), ("Gravelly alluvium", 4, 22), ("Weathered limestone", 22, 41), ("White limestone (karstic)", 41, 95)]


class Command(BaseCommand):
    """Create (or wipe) the DEMO dataset."""

    help = "Create twelve months of synthetic DEMO data. --wipe removes it. Idempotent: existing DEMO data is wiped first."

    def add_arguments(self, parser):
        """``--wipe`` only removes; ``--force`` allows running next to real data."""
        parser.add_argument("--wipe", action="store_true", help="Remove DEMO data and stop")
        parser.add_argument("--force", action="store_true", help="Run even if non-demo wells exist")

    def handle(self, *args, **options):
        """Wipe any previous demo set, then build a new one in one transaction."""
        self.rng = random.Random(2026)  # noqa: S311 # nosec B311
        self.today = date.today()
        self.tz = timezone.get_current_timezone()
        if not options["force"] and Well.objects.exclude(name__startswith=PREFIX).exists():
            raise CommandError("Database holds non-demo wells; refusing without --force.")
        with transaction.atomic():
            self._wipe()
            if options["wipe"]:
                self.stdout.write("DEMO data removed.")
                return
            self._lookups()
            self._users()
            self._sites()
            self._applications_and_licences()
            self._observations()
            self._field_records()
        self.stdout.write(self.style.SUCCESS(
            f"DEMO data ready: {Well.objects.filter(name__startswith=PREFIX).count()} wells, "
            f"{Licence.objects.filter(source_name__startswith=PREFIX).count()} licences, "
            f"{WellWaterLevel.objects.filter(well__name__startswith=PREFIX).count()} well levels, "
            f"{StationReading.objects.filter(station__name__startswith=PREFIX).count()} station readings. "
            f"Users demo.* / password from DEMO_PASSWORD."
        ))

    # ------------------------------------------------------------------ helpers
    def _dt(self, d: date, hour: int = 8) -> datetime:
        return timezone.make_aware(datetime.combine(d, time(hour, 0)), self.tz)

    def _wipe(self):
        wells = Well.objects.filter(name__startswith=PREFIX)
        stations = StreamflowStation.objects.filter(name__startswith=PREFIX)
        springs = Spring.objects.filter(name__startswith=PREFIX)
        ApprovalPeriod.objects.filter(well__in=wells).delete()
        ApprovalPeriod.objects.filter(station__in=stations).delete()
        WellWaterLevel.objects.filter(well__in=wells).delete()
        StationReading.objects.filter(station__in=stations).delete()
        WaterQualitySample.objects.filter(well__in=wells).delete()
        WaterQualitySample.objects.filter(station__in=stations).delete()
        WaterQualitySample.objects.filter(spring__in=springs).delete()
        apps_qs = LicenceApplication.objects.filter(source_name__startswith=PREFIX)
        AbstractionRecord.objects.filter(licence__application__in=apps_qs).delete()
        Licence.objects.filter(application__in=apps_qs).delete()
        from apps.workflow.models import WorkflowInstance

        WorkflowInstance.objects.filter(summary__startswith=PREFIX).delete()
        apps_qs.delete()
        InstrumentInstallation.objects.filter(instrument__serial_number__startswith=PREFIX).delete()
        Instrument.objects.filter(serial_number__startswith=PREFIX).delete()
        wells.delete()
        stations.delete()
        springs.delete()
        Party.objects.filter(name__startswith=PREFIX).delete()
        User.objects.filter(email__startswith="demo.").delete()

    def _lookups(self):
        """Make sure the reference lookups the demo refers to exist (load_reference_data normally does this)."""
        need = Parish.objects.count() < 14 or Basin.objects.count() < 10 or WMU.objects.count() < 10 or not River.objects.exists()
        if need:
            from django.core.management import call_command

            call_command("load_reference_data", verbosity=0)
        self.parish = {p.code: p for p in Parish.objects.all()}
        self.basin = {b.code: b for b in Basin.objects.all()}
        self.wmu = {w.code: w for w in WMU.objects.all()}
        self.river = {r.code: r for r in River.objects.all()}
        self.hsu = HydrostratUnit.objects.filter(code="LST").first()

    def _users(self):
        password = os.environ.get("DEMO_PASSWORD", "WaterSource-Demo-2026!")
        self.users = {}
        for email, name, utype, role in DEMO_USERS:
            u = User.objects.create_user(email=email, password=password, full_name=name, user_type=utype, email_verified_at=timezone.now(), phone="876-555-0100", organisation="WRA (demo)" if utype == UserType.STAFF else "Demo Farms Ltd")
            u.groups.add(Group.objects.get(name=role))
            self.users[role] = u
        self.users[roles.CLIENT].party = Party.objects.create(kind=PartyKind.APPLICANT, name=f"{PREFIX} Farms Ltd", email="demo.client@example.com", phone="876-555-0100", address="Old Harbour, St. Catherine", is_organisation=True)
        self.users[roles.CLIENT].save(update_fields=["party"])

    def _sites(self):
        driller = Party.objects.create(kind=PartyKind.DRILLER, name=f"{PREFIX} Drilling Co.", is_organisation=True)
        lab = Party.objects.create(kind=PartyKind.LABORATORY, name=f"{PREFIX} Water Laboratory", is_organisation=True)
        self.lab = lab
        self.wells = []
        for i, (name, parish, basin, wmu, use, e, n) in enumerate(WELLS):
            owner = Party.objects.create(kind=PartyKind.OWNER, name=f"{PREFIX} Owner {i + 1}", is_organisation=i % 2 == 0)
            w = Well.objects.create(
                name=f"{PREFIX} {name}", parish=self.parish[parish], basin=self.basin[basin], wmu=self.wmu.get(wmu), hydrostrat_unit=self.hsu,
                use=use, easting=e, northing=n, elevation_m=Decimal(self.rng.randint(5, 120)), current_owner=owner, driller=driller,
                pump_attached=use != WellUse.OBSERVATION, is_pumping=use != WellUse.OBSERVATION, is_index_well=use == WellUse.OBSERVATION,
                approval_state=ApprovalState.APPROVED, classification=Classification.PUBLIC, source=DataSource.MIGRATED,
            )
            for seq, (strata, top, bottom) in enumerate(LITHOLOGY, start=1):
                WellLithology.objects.create(well=w, sequence=seq, strata_type=strata, depth_from_m=top, depth_to_m=bottom, strata_thickness_m=bottom - top)
            WellCasing.objects.create(well=w, casing_type="Steel", diameter_mm=250, thickness_mm=6, depth_from_m=0, depth_to_m=40)
            WellCasing.objects.create(well=w, casing_type="Stainless screen", is_screen=True, diameter_mm=250, depth_from_m=40, depth_to_m=90)
            WellPumpTest.objects.create(well=w, tested_on=self.today - timedelta(days=self.rng.randint(400, 4000)), duration_hours=24, static_water_level_m=Decimal(self.rng.randint(8, 30)),
                                        constant_test_rate_m3_d=Decimal(self.rng.randint(800, 4000)), constant_test_drawdown_m=Decimal(self.rng.randint(2, 12)), tested_by=driller)
            drilled = self.today - timedelta(days=self.rng.randint(800, 9000))
            WellStatusEvent.objects.create(well=w, event=WellEvent.DRILLED, occurred_on=drilled, details="Rotary drilled")
            WellStatusEvent.objects.create(well=w, event=WellEvent.COMPLETED, occurred_on=drilled + timedelta(days=21))
            if w.pump_attached:
                WellStatusEvent.objects.create(well=w, event=WellEvent.PUMP_INSTALLED, occurred_on=drilled + timedelta(days=40), details="Submersible 30 kW")
            ReferencePoint.objects.create(well=w, description="Top of casing, north side", elevation_m=w.elevation_m + Decimal("0.45"), height_above_ground_m=Decimal("0.45"), valid_from=drilled + timedelta(days=21), surveyed_by="WRA survey")
            self.wells.append(w)
        self.stations = []
        for name, river, parish, basin, wmu, e, n in STATIONS:
            s = StreamflowStation.objects.create(
                name=f"{PREFIX} {name}", river=self.river[river], parish=self.parish[parish], basin=self.basin[basin], wmu=self.wmu.get(wmu),
                easting=e, northing=n, elevation_m=Decimal(self.rng.randint(20, 300)), aquarius_identifier=name.replace(" ", "_"),
                approval_state=ApprovalState.APPROVED, classification=Classification.PUBLIC, source=DataSource.MIGRATED,
            )
            ReferencePoint.objects.create(station=s, description="Gauge board zero", elevation_m=s.elevation_m, valid_from=date(2015, 1, 1))
            self.stations.append(s)
        self.springs = [Spring.objects.create(name=f"{PREFIX} {n}", parish=self.parish[p], approval_state=ApprovalState.APPROVED, classification=Classification.PUBLIC) for n, p in SPRINGS]

    def _applications_and_licences(self):
        client = self.users[roles.CLIENT]
        approver = self.users[roles.APPROVER]
        purposes = ["Irrigation of 40 ha sugar cane", "Public water supply", "Bottling plant process water", "Hotel domestic supply", "Poultry farm", "Aquaculture ponds"]
        self.licences = []
        # 40 applications, oldest first, spread over 12 months
        for i in range(40):
            submitted = self.today - timedelta(days=int(365 * (39 - i) / 39) + self.rng.randint(0, 6))
            well = self.wells[i % len(self.wells)] if i % 3 != 2 else None
            source = WaterSource.WELL if well else self.rng.choice([WaterSource.RIVER, WaterSource.SPRING])
            source_name = well.name if well else f"{PREFIX} {self.rng.choice(['Rio Cobre', 'Rio Minho', 'Black River', 'Roaring River Spring'])}"
            parish = well.parish if well else self.parish[self.rng.choice(["STC", "CLA", "STE"])]
            requested = Decimal(self.rng.randint(200, 5000))
            party = Party.objects.create(kind=PartyKind.APPLICANT, name=f"{PREFIX} Applicant {i + 1:02d}", email=f"applicant{i + 1}@example.com", phone="876-555-0199", address=f"{parish.name}")
            app = LicenceApplication(
                applicant_user=client if i % 4 == 0 else None, applicant=party if i % 4 else client.party, applicant_name=party.name if i % 4 else client.party.name,
                applicant_address=party.address if i % 4 else client.party.address, applicant_email=party.email if i % 4 else client.party.email, applicant_phone="876-555-0199",
                parish=parish, water_source=source, source_name=source_name, well=well, daily_volume_requested_m3=requested,
                purpose=self.rng.choice(purposes), submitted_at=self._dt(submitted, 10),
            )
            # status mix: first 25 granted, then 5 refused, 3 info requested, 4 under review (live workflow), 3 drafts
            if i < 25:
                decided = submitted + timedelta(days=self.rng.randint(20, 75))
                granted = requested if i % 5 else (requested * Decimal("0.8")).quantize(Decimal("0.001"))
                app.status, app.decided_at, app.daily_volume_granted_m3 = ApplicationStatus.GRANTED, self._dt(decided, 15), granted
                app.decision_remarks = "Granted subject to standard conditions."
                app.save()
                years = self.rng.choice([1, 2, 3, 5])
                issued = decided
                expires = date(issued.year + years, issued.month, min(issued.day, 28))
                if i in (3, 9):  # expired last month
                    expires = self.today - timedelta(days=self.rng.randint(5, 40))
                elif i in (12, 18):  # expiring within 30 days
                    expires = self.today + timedelta(days=self.rng.randint(5, 28))
                elif i in (6, 15, 21):  # expiring within 90 days
                    expires = self.today + timedelta(days=self.rng.randint(35, 85))
                lic = Licence.objects.create(
                    number=Sequence.next("licence", "DEMO-L"), application=app, licensee=app.applicant, parish=parish, water_source=source,
                    source_name=source_name, well=well, daily_volume_granted_m3=granted, purpose=app.purpose, issued_on=issued, expires_on=expires,
                    status=LicenceStatus.EXPIRED if expires < self.today else LicenceStatus.ACTIVE, issued_by=approver, classification=Classification.PUBLIC,
                )
                if well:
                    Well.objects.filter(pk=well.pk).update(is_licensed=True, licence_number=lic.number)
                    WellStatusEvent.objects.create(well=well, event=WellEvent.LICENSED, occurred_on=issued, details=lic.number)
                self.licences.append(lic)
            elif i < 30:
                app.status, app.decided_at, app.decision_remarks = ApplicationStatus.REFUSED, self._dt(submitted + timedelta(days=self.rng.randint(15, 60)), 15), "Aquifer already fully allocated."
                app.save()
            elif i < 33:
                app.status = ApplicationStatus.INFO_REQUESTED
                app.save()
            elif i < 37:
                app.status = ApplicationStatus.UNDER_REVIEW
                app.save()
                from apps.workflow import engine

                engine.start("licence_application", app, client, summary=f"{PREFIX} {app.reference} · {app.applicant_name} · {parish.name}")
            else:
                app.status, app.submitted_at = ApplicationStatus.DRAFT, None
                app.save()

    def _observations(self):
        hydro = self.users[roles.HYDROLOGIST]
        tech = self.users[roles.TECHNICIAN]
        start = self.today - timedelta(days=365)
        working_from = self.today - timedelta(days=30)  # last month left unapproved
        levels, readings, samples, abstractions = [], [], [], []
        for w in self.wells:
            base = float(self.rng.randint(6, 28))
            d = start
            while d <= self.today:
                # seasonal: deeper (larger number) in Mar–Apr, shallower after Oct–Nov rains
                seasonal = 1.8 * math.sin((d.timetuple().tm_yday - 60) / 365 * 6.283)
                value = round(base + seasonal + self.rng.gauss(0, 0.15), 3)
                grade = ObservationGrade.GOOD if self.rng.random() > 0.08 else self.rng.choice([ObservationGrade.FAIR, ObservationGrade.POOR, ObservationGrade.ESTIMATED])
                quals = ["PUMPING"] if (w.is_pumping and self.rng.random() < 0.1) else []
                approved = d < working_from
                levels.append(WellWaterLevel(
                    well=w, measured_at=self._dt(d, 9), water_level_m=Decimal(str(value)), well_state=WellState.NON_PUMPING if not quals else WellState.PUMPING,
                    measured_by=tech.full_name, grade=grade, qualifiers=quals, graded_by=hydro if approved else None, graded_at=self._dt(d, 12) if approved else None,
                    approval_state=ApprovalState.APPROVED if approved else ApprovalState.PENDING, classification=Classification.PUBLIC, source=DataSource.STAFF,
                ))
                d += timedelta(days=7)
        WellWaterLevel.objects.bulk_create(levels)
        for s in self.stations:
            base = float(self.rng.randint(40, 120)) / 100
            d = start
            while d <= self.today:
                wet = 1 if d.month in (5, 6, 9, 10, 11) else 0
                stage = round(base + 0.35 * wet + max(0.0, self.rng.gauss(0, 0.12)) + (0.9 if self.rng.random() < 0.02 else 0), 3)
                q = round(18.5 * (stage ** 1.6), 4)  # simple rating
                quals = ["FLOOD"] if stage > base + 1.0 else []
                approved = d < working_from
                readings.append(StationReading(
                    station=s, read_at=self._dt(d, 8), recorder_reading_m=Decimal(str(stage)), observer_reading_m=Decimal(str(round(stage + self.rng.gauss(0, 0.01), 3))) if d.day in (1, 15) else None,
                    discharge_m3_s=Decimal(str(q)), grade=ObservationGrade.GOOD if not quals else ObservationGrade.FAIR, qualifiers=quals,
                    graded_by=hydro if approved else None, graded_at=self._dt(d, 12) if approved else None,
                    approval_state=ApprovalState.APPROVED if approved else ApprovalState.PENDING, classification=Classification.PUBLIC, source=DataSource.AQUARIUS,
                ))
                d += timedelta(days=1)
        StationReading.objects.bulk_create(readings, batch_size=500)
        # abstraction: one row per month per active licence
        for lic in self.licences:
            if lic.status != LicenceStatus.ACTIVE:
                continue
            m = date(start.year, start.month, 1)
            over_month = self.rng.randint(0, 11) if self.rng.random() < 0.3 else None
            k = 0
            while m <= self.today:
                nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
                if nxt > self.today:
                    break
                days = (nxt - m).days
                factor = 1.25 if k == over_month else self.rng.uniform(0.55, 0.98)
                volume = (lic.daily_volume_granted_m3 * Decimal(days) * Decimal(str(round(factor, 3)))).quantize(Decimal("0.001"))
                allowed = lic.daily_volume_granted_m3 * days
                over = volume > allowed
                abstractions.append(AbstractionRecord(
                    licence=lic, well=lic.well, source_type=AbstractionSource.GROUND if lic.well_id else AbstractionSource.SURFACE,
                    period_start=self._dt(m, 0), period_end=self._dt(nxt, 0) - timedelta(seconds=1), abstraction_volume_m3=volume,
                    daily_volume_granted_m3=lic.daily_volume_granted_m3, over_limit=over, over_limit_pct=((volume / allowed - 1) * 100).quantize(Decimal("0.01")) if over else None,
                    grade=ObservationGrade.GOOD, approval_state=ApprovalState.APPROVED, classification=Classification.STAFF_ONLY, source=DataSource.SUBMISSION,
                ))
                m, k = nxt, k + 1
        AbstractionRecord.objects.bulk_create(abstractions)
        # water quality: quarterly
        sites = [(SampleSource.WELL, w) for w in self.wells] + [(SampleSource.SPRING, s) for s in self.springs] + [(SampleSource.STREAM, s) for s in self.stations]
        for kind, site in sites:
            for q in range(4):
                d = start + timedelta(days=45 + 91 * q)
                cond = self.rng.randint(300, 1400) if kind != SampleSource.STREAM else self.rng.randint(150, 500)
                samples.append(WaterQualitySample(
                    source_type=kind, well=site if kind == SampleSource.WELL else None, spring=site if kind == SampleSource.SPRING else None,
                    station=site if kind == SampleSource.STREAM else None, laboratory=self.lab, sample_ref=f"{PREFIX}-{site.pk}-{q + 1}",
                    sampled_at=self._dt(d, 10), analysed_at=self._dt(d + timedelta(days=4), 14), sampled_by=self.users[roles.TECHNICIAN].full_name,
                    specific_conductivity_us_cm=cond, temperature_c=Decimal(str(round(self.rng.uniform(24, 29), 1))), ph=Decimal(str(round(self.rng.uniform(6.8, 8.1), 2))),
                    nitrate_mg_l=Decimal(str(round(self.rng.uniform(1, 28), 2))), chloride_mg_l=Decimal(str(round(cond * 0.12, 2))), hardness_mg_l=Decimal(str(round(cond * 0.35, 1))),
                    total_dissolved_solids_mg_l=Decimal(str(round(cond * 0.64, 1))), turbidity_ntu=Decimal(str(round(self.rng.uniform(0.2, 6), 2))),
                    grade=ObservationGrade.GOOD, approval_state=ApprovalState.APPROVED, classification=Classification.PUBLIC, source=DataSource.SUBMISSION,
                ))
        WaterQualitySample.objects.bulk_create(samples)
        # approval periods for the approved months
        for w in self.wells:
            ApprovalPeriod.objects.create(series=SeriesKind.WELL_LEVEL, well=w, starts_at=self._dt(start, 0), ends_at=self._dt(working_from, 0), approved_by=hydro, rows_approved=WellWaterLevel.objects.filter(well=w, approval_state=ApprovalState.APPROVED).count())
        for s in self.stations:
            ApprovalPeriod.objects.create(series=SeriesKind.STATION_STAGE, station=s, starts_at=self._dt(start, 0), ends_at=self._dt(working_from, 0), approved_by=hydro, rows_approved=StationReading.objects.filter(station=s, approval_state=ApprovalState.APPROVED).count())

    def _field_records(self):
        tech = self.users[roles.TECHNICIAN]
        instruments = []
        for i, w in enumerate(self.wells[:6]):
            inst = Instrument.objects.create(kind=InstrumentKind.LEVEL_LOGGER, make="Solinst", model="Levelogger 5", serial_number=f"{PREFIX}-LL-{i + 1:03d}", calibration_due_on=self.today + timedelta(days=self.rng.randint(-20, 300)))
            InstrumentInstallation.objects.create(instrument=inst, well=w, installed_on=self.today - timedelta(days=self.rng.randint(90, 700)), sensor_offset_m=Decimal("-35.000"))
            instruments.append(inst)
        for i, s in enumerate(self.stations):
            inst = Instrument.objects.create(kind=InstrumentKind.STAGE_RECORDER, make="OTT", model="RLS radar", serial_number=f"{PREFIX}-RLS-{i + 1:03d}", calibration_due_on=self.today + timedelta(days=self.rng.randint(30, 365)))
            InstrumentInstallation.objects.create(instrument=inst, station=s, installed_on=self.today - timedelta(days=self.rng.randint(200, 900)))
        purposes = list(VisitPurpose)
        for w in self.wells:
            for k in range(4):
                d = self.today - timedelta(days=30 + 90 * k + self.rng.randint(0, 10))
                SiteVisit.objects.create(well=w, visited_on=d, visited_by=tech, purpose=purposes[self.rng.randrange(len(purposes))], findings="Site accessible; casing sound; reading taken.", follow_up="Replace padlock" if k == 0 and self.rng.random() < 0.3 else "", follow_up_due_on=self.today + timedelta(days=14) if k == 0 and self.rng.random() < 0.3 else None)
        for s in self.stations:
            for k in range(6):
                d = self.today - timedelta(days=15 + 60 * k + self.rng.randint(0, 10))
                SiteVisit.objects.create(station=s, visited_on=d, visited_by=tech, purpose=VisitPurpose.GAUGING if k % 2 else VisitPurpose.ROUTINE, findings="Gauging completed; control stable.")
