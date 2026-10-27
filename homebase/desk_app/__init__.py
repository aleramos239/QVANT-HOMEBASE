"""The desk server's parts; homebase.server.create_app assembles them (uvicorn homebase.server:app).

readiness: the pre-open checks. barsfeed: the bars price feed. brokers: account connect / login budget / gone
accounts / paper sync / the reconnect loop. background: the loops and the lifespan. Moved verbatim from
homebase/server.py; nothing here imports homebase.server."""
