"""Fake Slurm for unit tests: jobs live in a dict; cancel just records."""


class FakeSlurm:
    SlurmError = RuntimeError

    def __init__(self):
        self.jobs = {}
        self.cancelled = []
        self.submitted = []

    def add(self, job_id, user, state="RUNNING", licenses="vcu118:1", time_limit="00:30:00", name="kotl-run"):
        self.jobs[job_id] = {"JobId": str(job_id), "User": user, "UserId": f"{user}(1000)",
                             "JobState": state, "Licenses": licenses, "TimeLimit": time_limit, "JobName": name}

    def job_info(self, job_id):
        return self.jobs.get(int(job_id))

    def state(self, job_id):
        j = self.jobs.get(int(job_id))
        return j["JobState"] if j else ""

    def cancel(self, job_id, signal=None):
        self.cancelled.append(int(job_id))
        return True

    def queue(self):
        return [{"job": str(k), "user": v["User"], "name": v["JobName"], "state": v["JobState"],
                 "eta": v["TimeLimit"], "used": "0:01", "start": "N/A", "reason": "None"}
                for k, v in self.jobs.items()]

    def submit(self, script, args, **kw):
        self.submitted.append({"script": script, "args": list(args), **kw})
        return 100 + len(self.submitted)
