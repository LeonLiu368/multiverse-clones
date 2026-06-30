"""aws-clone IAM hybrid shim.

Self-contained package shipped INSIDE /opt/awscli so it travels with the AWS tools into agent
containers. ``install()`` monkeypatches botocore client creation to register IAM-only handlers that
serve the operations moto/LocalStack lacks (simulate-principal-policy, simulate-custom-policy,
generate/get-credential-report). It is idempotent and never breaks client creation on failure; it
only touches those four IAM operations — every other call passes through to LocalStack unchanged.
"""
from __future__ import annotations

__all__ = ["install"]

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    try:
        import botocore.client as botocore_client
    except Exception:
        return
    original_init = botocore_client.BaseClient.__init__
    if getattr(original_init, "_aws_clone_shim", False):
        _installed = True
        return

    def patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        original_init(self, *args, **kwargs)
        try:
            from .handlers import register

            register(self)
        except Exception:
            pass

    patched_init._aws_clone_shim = True  # type: ignore[attr-defined]
    botocore_client.BaseClient.__init__ = patched_init
    _installed = True
