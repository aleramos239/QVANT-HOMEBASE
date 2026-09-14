"""Homebase — the live desk: runs the approved strategies against the broker.

Broker layer (homebase/broker/*, symbols, contracts, secrets_store, risk) is
extracted from the battle-tested copier at snapshot 0a75af5; everything else
is new. Deliberately separate from onyx/ (research loop) and base/ (read-only
dashboard).
"""
