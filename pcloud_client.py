import os
import time
from pathlib import Path
import requests
from hashlib import sha1
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


class PCloudSession(requests.Session):
    """
    Session that automatically injects valid authentication credentials
    (digest-based or access_token) into every request targeting pCloud API endpoints.
    """

    def __init__(self, client):
        super().__init__()
        self.client = client

    def request(self, method, url, **kwargs):
        if "pcloud.com" in url:
            auth_params = self.client.get_auth_params()
            if method.upper() == "GET":
                params = kwargs.get("params") or {}
                kwargs["params"] = {**auth_params, **params}
            elif method.upper() in ("POST", "PUT"):
                data = kwargs.get("data") or {}
                if isinstance(data, dict):
                    kwargs["data"] = {**auth_params, **data}
        return super().request(method, url, **kwargs)


class PyCloud:
    """
    pCloud API client supporting modern digest authentication and OAuth2.
    Drop-in compatible with tomgross/pcloud library interface.
    """

    def __init__(
        self,
        email: str = None,
        password: str = None,
        access_token: str = None,
        endpoint: str = "https://api.pcloud.com/",
    ):
        self.email = email or os.getenv("PCLOUD_EMAIL")
        self.password = password or os.getenv("PCLOUD_PASSWORD")
        self.access_token = access_token or os.getenv("PCLOUD_ACCESS_TOKEN")
        self.endpoint = endpoint.rstrip("/") + "/"
        self._digest = None
        self._digest_time = 0
        self.session = PCloudSession(self)

        # Authenticate and cache user information
        self.user_info = self.get_user_info()

    def _get_digest(self) -> str:
        """Fetch a 30-second digest token from pCloud server, caching for up to 25 seconds."""
        now = time.time()
        if self._digest and (now - self._digest_time) < 25:
            return self._digest

        r = requests.get(self.endpoint + "getdigest", timeout=15).json()
        if r.get("result") != 0:
            raise RuntimeError(f"Failed to retrieve digest from pCloud: {r}")

        self._digest = r["digest"]
        self._digest_time = now
        return self._digest

    def get_auth_params(self) -> dict:
        """Return dict of query/POST parameters required to authenticate the request."""
        if self.access_token:
            return {"access_token": self.access_token}

        if not self.email or not self.password:
            raise ValueError(
                "pCloud credentials missing. Please set PCLOUD_EMAIL and PCLOUD_PASSWORD in .env or pass to constructor."
            )

        digest = self._get_digest()
        username = self.email.lower()
        inner_hash = sha1(username.encode("utf-8")).hexdigest()
        combined = (
            self.password.encode("utf-8")
            + inner_hash.encode("utf-8")
            + digest.encode("utf-8")
        )
        passworddigest = sha1(combined).hexdigest()

        return {
            "username": self.email,
            "digest": digest,
            "passworddigest": passworddigest,
        }

    def _request(
        self, method_name: str, params: dict = None, data: dict = None, files=None, http_method: str = "GET"
    ) -> dict:
        url = self.endpoint + method_name
        if http_method == "GET":
            resp = self.session.get(url, params=params)
        else:
            resp = self.session.post(url, data=data, files=files)

        data = resp.json()
        # If digest expired between requests, retry once with a fresh digest
        if data.get("result") == 2000 and not self.access_token:
            self._digest = None
            if http_method == "GET":
                resp = self.session.get(url, params=params)
            else:
                resp = self.session.post(url, data=data, files=files)
            data = resp.json()

        return data

    def get_user_info(self) -> dict:
        """Get account information for the authenticated user."""
        res = self._request("userinfo")
        if res.get("result") != 0:
            raise ConnectionRefusedError(f"pCloud Authentication failed: {res}")
        return res

    def listfolder(self, folderid: int = 0, path: str = None) -> dict:
        """List metadata and contents of a folder by folder ID or path."""
        params = {}
        if path is not None:
            params["path"] = path
        else:
            params["folderid"] = folderid
        return self._request("listfolder", params=params)

    def createfolder(self, folderid: int = None, path: str = None) -> dict:
        """Create folder by path or folder ID."""
        params = {}
        if path is not None:
            params["path"] = path
        if folderid is not None:
            params["folderid"] = folderid
        return self._request("createfolder", params=params)

    def uploadfile(self, files: list, folderid: int = 0, path: str = None) -> dict:
        """Upload one or more local files into a pCloud folder."""
        data = {}
        if path is not None:
            data["path"] = path
        else:
            data["folderid"] = str(folderid)

        file_handles = []
        upload_files = []
        try:
            for f in files:
                if isinstance(f, str):
                    fh = open(f, "rb")
                    file_handles.append(fh)
                    filename = os.path.basename(f)
                    upload_files.append(("file", (filename, fh)))
                else:
                    upload_files.append(("file", f))
            return self._request(
                "uploadfile", data=data, files=upload_files, http_method="POST"
            )
        finally:
            for fh in file_handles:
                fh.close()

    def deletefile(self, fileid: int = None, path: str = None) -> dict:
        """Delete a file by file ID or path."""
        params = {}
        if fileid is not None:
            params["fileid"] = fileid
        if path is not None:
            params["path"] = path
        return self._request("deletefile", params=params)

    def getfilepublink(self, fileid: int, **kwargs) -> dict:
        """Generate a public sharing link for a file."""
        params = {"fileid": fileid, **kwargs}
        return self._request("getfilepublink", params=params)

    def changepublink(self, linkid: int, **kwargs) -> dict:
        """Modify a public sharing link (e.g. generate shortlink)."""
        params = {"linkid": linkid, **kwargs}
        return self._request("changepublink", params=params)


# Alias PCloudClient for flexibility
PCloudClient = PyCloud
