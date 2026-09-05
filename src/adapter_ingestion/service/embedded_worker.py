# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import threading
import time

from .job_processor import process_one_job
from .observability import log_event


def should_enable_embedded_worker(settings) -> bool:  # type: ignore[no-untyped-def]
    local_tokens = {"mem", "fs"}
    return (
        str(settings.db_provider or "").strip().lower() in local_tokens
        and str(settings.queue_provider or "").strip().lower() in local_tokens
        and str(settings.storage_provider or "").strip().lower() in local_tokens
    )


def install_embedded_worker(app, *, control_plane, blob_store, vault_repo, subject_link_store, settings) -> None:  # type: ignore[no-untyped-def]
    if not should_enable_embedded_worker(settings):
        return

    stop_event = threading.Event()
    worker_id = os.getenv("HOSTNAME", "preconv-api-embedded-worker")

    def _loop() -> None:
        log_event("embedded_worker_started", workerId=worker_id)
        while not stop_event.is_set():
            processed_job_id = process_one_job(
                control_plane=control_plane,
                blob_store=blob_store,
                vault_repo=vault_repo,
                subject_link_store=subject_link_store,
                settings=settings,
                worker_id=worker_id,
            )
            if not processed_job_id:
                stop_event.wait(0.2)
        log_event("embedded_worker_stopped", workerId=worker_id)

    @app.on_event("startup")
    def _start_embedded_worker() -> None:
        if getattr(app.state, "embedded_worker_thread", None):
            return
        thread = threading.Thread(target=_loop, name="preconv-embedded-worker", daemon=True)
        app.state.embedded_worker_thread = thread
        app.state.embedded_worker_stop_event = stop_event
        thread.start()

    @app.on_event("shutdown")
    def _stop_embedded_worker() -> None:
        stop_event.set()
        thread = getattr(app.state, "embedded_worker_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
