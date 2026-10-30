"""Public, credential-free authentication failures."""


class DeviceAuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail
