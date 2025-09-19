from locust import HttpUser, task, between
import os
import base64


def _auth_header():
    user = os.getenv("ADMIN_USER", "")
    pw = os.getenv("ADMIN_PASS", "")
    if not user or not pw:
        return {}
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class HOSUser(HttpUser):
    wait_time = between(1, 2)

    @task(3)
    def health(self):
        self.client.get("/api/health")

    @task(2)
    def logs(self):
        headers = _auth_header()
        if headers:
            self.client.get("/api/logs?limit=1", headers=headers)

    @task(2)
    def stats(self):
        headers = _auth_header()
        if headers:
            self.client.get("/api/stats", headers=headers)


