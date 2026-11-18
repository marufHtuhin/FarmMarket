"""AI services for FarmMarket: offline training pipelines (PyTorch, Prophet, ...).

These packages are training/inference tooling, NOT part of the FastAPI app.
The backend only depends on them through the thin `app.services.torch_vision`
wrapper, which imports torch lazily so the API runs without torch installed.
"""
