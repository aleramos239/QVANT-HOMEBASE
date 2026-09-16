"""Homebase — the live desk: runs the approved strategies against the broker.

Broker layer (homebase/broker/*, symbols, contracts, secrets_store, risk) is
extracted from the battle-tested copier at snapshot 0a75af5; everything else
is new. Deliberately separate from onyx/ (research loop) and base/ (read-only
dashboard).
"""
import os as _os

# python.org macOS builds ship no CA bundle for urllib/ssl; point the stdlib
# at certifi's so every entry point (server, scripts, timer) verifies TLS.
try:
    import certifi as _certifi
    _os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
except ImportError:  # pragma: no cover
    pass
