"""Load profile for the 3,000-concurrent-user target (docs/performance.md).
Run: locust -f loadtest/locustfile.py --host https://staging.example --users 3000 --spawn-rate 50
"""
import random

from locust import HttpUser, between, task


class PublicVisitor(HttpUser):
    weight = 6
    wait_time = between(5, 30)

    @task(4)
    def home(self):
        self.client.get("/")

    @task(3)
    def api_wells(self):
        self.client.get("/api/v1/wells/?page=" + str(random.randint(1, 5)))  # noqa: S311

    @task(2)
    def api_levels(self):
        self.client.get("/api/v1/observations/well-water-levels/")


class Client(HttpUser):
    weight = 3
    wait_time = between(10, 60)

    def on_start(self):
        r = self.client.get("/accounts/login/")
        token = r.cookies.get("csrftoken")
        self.client.post("/accounts/login/", {"username": "client@example.com", "password": "Cl1ent-Passw0rd!x", "csrfmiddlewaretoken": token}, headers={"Referer": self.host})

    @task(3)
    def submissions(self):
        self.client.get("/submissions/")

    @task(2)
    def applications(self):
        self.client.get("/licensing/applications/")

    @task(1)
    def form(self):
        self.client.get("/submissions/water_quality/new/")


class Staff(HttpUser):
    weight = 1
    wait_time = between(3, 20)

    def on_start(self):
        r = self.client.get("/accounts/login/")
        token = r.cookies.get("csrftoken")
        self.client.post("/accounts/login/", {"username": "reviewer@wra.gov.jm", "password": "Rev1ew-Passw0rd!x", "csrfmiddlewaretoken": token}, headers={"Referer": self.host})

    @task
    def queue(self):
        self.client.get("/workflow/queue/")
