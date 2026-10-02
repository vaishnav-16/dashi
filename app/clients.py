"""Shared clients for Dashi: the VSS backend (JWT auth) and W&B inference (LLM).

Used by main.py in the pod and by core.py / analyze.py on the VM. Credentials come from
VSS_URL / VSS_USERNAME / VSS_PASSWORD (pod Secret), else the single /config/*.config team
file, else INGRESS_URL / USERNAME / PASSWORD in the environment. Never log their values.
"""
import glob
import os
import re
import threading
import urllib.parse

import requests

WANDB_BASE_URL = "https://api.inference.wandb.ai/v1"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
MODEL = os.environ.get("DASHI_MODEL") or DEFAULT_MODEL


def _team_config():
    files = sorted(glob.glob("/config/*.config"))
    if len(files) != 1:
        return {}
    cfg = {}
    with open(files[0]) as f:
        for line in f:
            m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)=(.*)", line)
            if m:
                cfg[m.group(1)] = m.group(2).strip().strip("\"'")
    return cfg


_CFG = _team_config()


def setting(pod_name, vm_name=None):
    """Pod env var first, then the team config file, then the VM env var."""
    vm_name = vm_name or pod_name
    return os.environ.get(pod_name) or _CFG.get(vm_name) or os.environ.get(vm_name) or ""


class VSSError(RuntimeError):
    pass


class VSS:
    """Thin VSS backend client. Paths are relative to /api/v1."""

    def __init__(self, timeout=30):
        self.url = setting("VSS_URL", "INGRESS_URL").rstrip("/")
        self.username = setting("VSS_USERNAME", "USERNAME")
        self.password = setting("VSS_PASSWORD", "PASSWORD")
        self.timeout = timeout
        self._token = None
        self._lock = threading.Lock()

    @property
    def api(self):
        return self.url + "/api/v1"

    def _login(self):
        if not (self.url and self.username and self.password):
            raise VSSError("VSS credentials are not configured")
        r = requests.post(self.api + "/auth/login",
                          json={"username": self.username, "password": self.password},
                          timeout=self.timeout)
        if r.status_code != 200:
            raise VSSError(f"VSS login failed with HTTP {r.status_code}")
        self._token = r.json()["access_token"]

    def token(self):
        with self._lock:
            if not self._token:
                self._login()
            return self._token

    def _request(self, method, path, **kwargs):
        url = self.api + "/" + path.lstrip("/")
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self.token()}"}
            r = requests.request(method, url, headers=headers,
                                 timeout=kwargs.pop("timeout", self.timeout), **kwargs)
            if r.status_code == 401 and attempt == 0:
                with self._lock:
                    self._token = None
                continue
            if r.status_code >= 400:
                raise VSSError(f"{method} {path} returned HTTP {r.status_code}: {r.text[:200]}")
            return r.json()

    def get(self, path, **params):
        return self._request("GET", path, params=params)

    def post(self, path, json=None):
        return self._request("POST", path, json=json or {})

    def stream_path(self, source):
        """Same-host path the browser can put in <video src>; the token rides in the query."""
        q = urllib.parse.urlencode({"source": source, "token": self.token()})
        return f"/api/v1/videos/stream?{q}"


def llm(timeout=30):
    """OpenAI-compatible client for W&B serverless inference."""
    import openai

    team = setting("WANDB_TEAM")
    project = setting("WANDB_PROJECT")
    return openai.OpenAI(base_url=WANDB_BASE_URL,
                         api_key=setting("WANDB_API_KEY"),
                         project=f"{team}/{project}" if team and project else None,
                         timeout=timeout, max_retries=0)
