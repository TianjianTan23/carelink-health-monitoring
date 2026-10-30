"""Constant-only sensor ingress diagnostics: no headers, bodies or credentials."""
import logging

LOG = logging.getLogger('carelink.device')
STAGES = frozenset({'request_received', 'hmac_timestamp_verified',
                    'nonce_reserved', 'readings_committed', 'http_complete',
                    'authentication_rejected', 'storage_unavailable'})


def event(stage, status=None):
    if stage not in STAGES or (status is not None and type(status) is not int):
        raise ValueError('Invalid diagnostic event')
    LOG.info('[CareLink] stage=%s%s', stage,
             '' if status is None else ' status='+str(status))


def configure():
    # Dedicated logger: do not enable HTTP library debug or credential logging.
    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


class DeviceIngressDiagnostics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/sensor-data':
            return await self.app(scope, receive, send)
        event('request_received')
        async def observed(message):
            if message['type'] == 'http.response.start':
                event('http_complete', message['status'])
            await send(message)
        return await self.app(scope, receive, observed)
