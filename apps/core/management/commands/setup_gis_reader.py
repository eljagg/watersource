"""``manage.py setup_gis_reader`` — create or update the read-only database role for QGIS / ArcGIS Pro (design doc 15 §3.3).

The role can ``SELECT`` every table in ``public`` and ``bi`` (and any created
later, via default privileges) and nothing else. Public-supply coordinates are
in ``ref_well`` / ``ref_streamflowstation`` in full; analysts who may not see
them should instead be pointed at ``bi.public_wells`` / ``bi.public_stations``
(coarsened) — use ``--public-only`` to grant only those plus the lookups.

Example::

    manage.py setup_gis_reader --password 'long-random-string'
    manage.py setup_gis_reader --role gis_public --public-only --password '…'

Requires the application database user to own the tables or be a superuser
(true on Railway and on the app-vm as deployed). Idempotent: re-run to rotate
the password or re-apply grants.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core import audit

PUBLIC_ONLY_TABLES = ["ref_parish", "ref_basin", "ref_wmu", "ref_subwmu", "ref_river", "ref_hydrostratunit"]


class Command(BaseCommand):
    """Create the ``gis_reader`` role."""

    help = "Create/update the read-only gis_reader role used by QGIS and ArcGIS Pro."

    def add_arguments(self, parser):
        """CLI options."""
        parser.add_argument("--role", default="gis_reader")
        parser.add_argument("--password", required=True)
        parser.add_argument("--public-only", action="store_true", help="Grant only bi.public_* views and the boundary lookups")

    def handle(self, *args, **opts):
        """Create the role and apply grants."""
        role, pw = opts["role"], opts["password"]
        if not role.isidentifier():
            raise CommandError("Role name must be a plain identifier.")
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            exists = cur.fetchone() is not None
            quoted = connection.ops.quote_name(role)
            if exists:
                cur.execute(f"ALTER ROLE {quoted} WITH LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT", [pw])
            else:
                cur.execute(f"CREATE ROLE {quoted} WITH LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT", [pw])
            cur.execute(f"GRANT CONNECT ON DATABASE {connection.ops.quote_name(connection.settings_dict['NAME'])} TO {quoted}")
            cur.execute(f"GRANT USAGE ON SCHEMA public, bi TO {quoted}")
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {quoted}")
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA bi FROM {quoted}")
            if opts["public_only"]:
                for t in PUBLIC_ONLY_TABLES:
                    cur.execute(f"GRANT SELECT ON public.{t} TO {quoted}")
                cur.execute(f"GRANT SELECT ON bi.public_wells, bi.public_stations TO {quoted}")
            else:
                cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {quoted}")
                cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA bi TO {quoted}")
                cur.execute(f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {quoted}")
                cur.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO {quoted}")
                # never expose personal data or secrets to the GIS desk
                for t in ("accounts_user", "accounts_apikey", "accounts_emailtoken", "accounts_passwordhistory", "django_session",
                          "axes_accessattempt", "axes_accesslog", "axes_accessfailurelog", "core_auditlog", "core_notification"):
                    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s", [t])
                    if cur.fetchone():
                        cur.execute(f"REVOKE ALL ON public.{t} FROM {quoted}")
            # allow QGIS to save shared layer styles (table created on first 'Save style → in database' by an admin)
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'layer_styles'")
            if cur.fetchone():
                cur.execute(f"GRANT SELECT ON public.layer_styles TO {quoted}")
        audit.log("gis.reader_role_updated", None, summary=f"{role} ({'public only' if opts['public_only'] else 'full read'})")
        self.stdout.write(self.style.SUCCESS(f"Role {role} ready ({'bi.public_* and lookups' if opts['public_only'] else 'read-only on public + bi, personal data revoked'})."))
