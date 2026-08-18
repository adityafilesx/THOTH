import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from omnimac_daemon.api import (
    commands,
    health,
    intent,
    operational,
    permissions,
    runtime,
    skills,
    tasks,
    voice,
    ws,
)
from omnimac_daemon.api import settings as settings_api
from omnimac_daemon.api.middleware import BearerAuthMiddleware
from omnimac_daemon.audit.store import AuditStore
from omnimac_daemon.config import Settings
from omnimac_daemon.core.application_profiles import build_default_application_profiles
from omnimac_daemon.core.approvals import ApprovalEngine
from omnimac_daemon.core.ax_controller import AXController
from omnimac_daemon.core.ax_diagnostics import AXDiagnosticsStore
from omnimac_daemon.core.claude_planner import AnthropicPlannerClient, ClaudePlanner
from omnimac_daemon.core.command_dispatch import CommandDispatcher
from omnimac_daemon.core.dialogue import DialogueExpired, OperationalDialogueStore
from omnimac_daemon.core.focus import FocusManager
from omnimac_daemon.core.foreground import ForegroundContext, ForegroundContextBroker
from omnimac_daemon.core.local_plan_client import OllamaPlanClient
from omnimac_daemon.core.local_planner import LocalPlanner
from omnimac_daemon.core.local_runtime import (
    InferenceRuntimeDriver,
    LocalAIRuntimeManager,
    RuntimeComponent,
    RuntimeRegistration,
    SpeechRecognitionRuntimeDriver,
    SpeechSynthesisRuntimeDriver,
)
from omnimac_daemon.core.orchestrator import Orchestrator
from omnimac_daemon.core.planner import DeterministicMockPlanner, PlannerAdapter
from omnimac_daemon.core.policy import PolicyEngine
from omnimac_daemon.core.recovery import RecoveryController
from omnimac_daemon.core.runtime_status import LocalRuntimeMonitor
from omnimac_daemon.core.scope import ScopeEnforcer
from omnimac_daemon.core.skill_engine import seed_builtin_skills
from omnimac_daemon.core.verification import VerificationEngine
from omnimac_daemon.core.workspace_matching import (
    WorkspaceAssociationProfile,
    WorkspaceEvidence,
    WorkspaceMatcher,
)
from omnimac_daemon.events.bus import EventBus
from omnimac_daemon.inference import (
    DeterministicInferenceProvider,
    InferenceProvider,
    LlamaCppInferenceProvider,
    MLXInferenceProvider,
)
from omnimac_daemon.logging_setup import configure_logging, get_logger
from omnimac_daemon.macos.app_control import default_app_control
from omnimac_daemon.macos.ax_helper import AXHelperClient, AXHelperSemanticAXAdapter
from omnimac_daemon.macos.ax_permission import AXPermissionService
from omnimac_daemon.schemas import ResourceScope, WorkspaceProfile
from omnimac_daemon.security.auth import mint_token, write_token_file
from omnimac_daemon.security.paths import expand_and_resolve
from omnimac_daemon.storage.db import init_schema, make_engine, make_session_factory
from omnimac_daemon.storage.permissions import PermissionStore
from omnimac_daemon.storage.skills import SkillStore
from omnimac_daemon.tools.app_tools import register_app_tools
from omnimac_daemon.tools.browser_interaction_tools import register_browser_interaction_tools
from omnimac_daemon.tools.browser_tools import register_browser_tools
from omnimac_daemon.tools.fs_tools import register_fs_tools
from omnimac_daemon.tools.git_tools import register_git_tools
from omnimac_daemon.tools.mock_tools import build_registry
from omnimac_daemon.tools.research_tools import register_research_tools
from omnimac_daemon.tools.semantic_ax_tools import register_semantic_ax_tools
from omnimac_daemon.tools.shell_tool import register_shell_tool
from omnimac_daemon.voice.contracts import SpeechVoice
from omnimac_daemon.voice.metrics import VoiceLatencyMetrics
from omnimac_daemon.voice.service import VoiceCommandService, VoiceSessionRegistry
from omnimac_daemon.voice.stop import GlobalStopAuthority
from omnimac_daemon.voice.stt import (
    SpeechRecognitionSTTAdapter,
    WhisperCppSpeechRecognitionProvider,
)
from omnimac_daemon.voice.tts import MacOSSpeechSynthesisProvider, SpeechSynthesisService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(cfg.log_dir, cfg.log_level)
        log = get_logger("omnimac.app")
        engine = make_engine(cfg.db_path)
        await init_schema(engine)
        session_factory = make_session_factory(engine)
        bus = EventBus()
        app.state.settings = cfg
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.bus = bus

        # Per-session auth token: env-provided (dev/tests) or minted, then
        # written 0600 for the desktop to read (threat T6).
        token = cfg.session_token or mint_token()
        app.state.session_token = token
        write_token_file(cfg.session_token_path, token)

        async def publish(event_type: str, payload: dict[str, Any]) -> None:
            await bus.publish(event_type, payload)

        permissions_store = PermissionStore(session_factory)
        existing = await permissions_store.list_workspaces()
        configured_profiles: list[WorkspaceProfile] = []
        for configured_path in cfg.trusted_workspaces:
            normalized = str(expand_and_resolve(configured_path))
            match = next(
                (workspace for workspace in existing if workspace.root_path and str(expand_and_resolve(workspace.root_path)) == normalized),
                None,
            )
            if match is None:
                match = WorkspaceProfile(
                    name=expand_and_resolve(configured_path).name or "default",
                    root_path=normalized,
                    trusted=True,
                )
            elif match.root_path != normalized or not match.trusted:
                match = match.model_copy(update={"root_path": normalized, "trusted": True})
            await permissions_store.upsert_workspace(match)
            configured_profiles.append(match)

        if configured_profiles:
            default_ws = configured_profiles[0]
        elif existing:
            default_ws = existing[0]
        else:
            default_ws = WorkspaceProfile(
                name="default",
                root_path="",
                trusted=False,
            )
            await permissions_store.upsert_workspace(default_ws)
        app.state.permissions = permissions_store
        app.state.skills = SkillStore(session_factory)
        await seed_builtin_skills(app.state.skills)  # idempotent (Phase 4 slice 5)

        app.state.voice_metrics = VoiceLatencyMetrics()
        app.state.speech_synthesis_provider = MacOSSpeechSynthesisProvider()
        app.state.speech_synthesis = SpeechSynthesisService(
            app.state.speech_synthesis_provider,
            voice=SpeechVoice(identifier="Daniel", display_name="Daniel", language="en-GB"),
            metrics=app.state.voice_metrics,
        )
        app.state.speech_recognition = WhisperCppSpeechRecognitionProvider(
            executable=cfg.whisper_executable,
            model_path=cfg.whisper_model_path,
            language=cfg.whisper_language,
            expected_executable_sha256=cfg.whisper_executable_sha256,
            expected_model_sha256=cfg.whisper_model_sha256,
        )
        app.state.stt = SpeechRecognitionSTTAdapter(app.state.speech_recognition)
        audit_store = AuditStore(session_factory)
        app.state.audit = audit_store

        # Minimal Phase 5 runtime/presentation state. Provider selection is
        # explicit and local; there is no cloud fallback.
        inference_provider: InferenceProvider
        if cfg.inference_provider == "llama.cpp":
            inference_provider = LlamaCppInferenceProvider(
                model=cfg.inference_model,
                endpoint=cfg.inference_endpoint,
                isolation=cfg.network_isolation,
            )
        elif cfg.inference_provider == "mlx":
            inference_provider = MLXInferenceProvider(model=cfg.inference_model)
        else:
            inference_provider = DeterministicInferenceProvider()
        app.state.inference_provider = inference_provider
        app.state.runtime_monitor = LocalRuntimeMonitor(inference_provider)
        app.state.local_runtime = LocalAIRuntimeManager(
            memory_limit_bytes=12 * 1024 * 1024 * 1024,
            max_heavy_concurrency=1,
            offline=cfg.network_isolation,
        )
        speech_health = await app.state.speech_recognition.health()
        app.state.local_runtime.register(
            RuntimeRegistration(
                component=RuntimeComponent.PLANNER,
                display_name=cfg.inference_model,
                driver=InferenceRuntimeDriver(inference_provider),
                memory_estimate_bytes=4 * 1024 * 1024 * 1024,
                integrity_verified=True if cfg.inference_provider == "deterministic" else None,
                heavy=True,
            )
        )
        app.state.local_runtime.register(
            RuntimeRegistration(
                component=RuntimeComponent.SPEECH_RECOGNITION,
                display_name=cfg.whisper_model_path.name,
                driver=SpeechRecognitionRuntimeDriver(app.state.speech_recognition),
                memory_estimate_bytes=500 * 1024 * 1024,
                integrity_verified=(speech_health.available if app.state.speech_recognition.integrity_pinned else None),
                heavy=True,
            )
        )
        app.state.local_runtime.register(
            RuntimeRegistration(
                component=RuntimeComponent.TEXT_TO_SPEECH,
                display_name="macOS local speech",
                driver=SpeechSynthesisRuntimeDriver(app.state.speech_synthesis_provider),
                memory_estimate_bytes=64 * 1024 * 1024,
                integrity_verified=True,
                heavy=False,
            )
        )
        app.state.speech_synthesis.bind_runtime(app.state.local_runtime)
        app.state.dialogue = OperationalDialogueStore()
        app.state.application_profiles = build_default_application_profiles()
        app.state.default_workspace = default_ws
        app.state.focus_results = {}

        association_profiles: list[WorkspaceAssociationProfile] = []
        if default_ws.root_path:
            association_profiles.append(
                WorkspaceAssociationProfile(
                    workspace_id=default_ws.id,
                    approved_root_path=default_ws.root_path,
                    aliases=(default_ws.name,),
                    app_bundle_ids=("com.microsoft.VSCode",),
                    title_hints=(default_ws.name,),
                    approved=default_ws.trusted,
                    verified_at=datetime.now(UTC),
                )
            )
        workspace_matcher = WorkspaceMatcher(association_profiles)

        def match_workspace(context: ForegroundContext) -> str | None:
            match = workspace_matcher.match(
                WorkspaceEvidence(
                    active_bundle_id=context.active_bundle_id,
                    redacted_window_title=context.active_window_title,
                    approved_workspace_path=(default_ws.root_path if context.task_id and default_ws.root_path else None),
                    task_workspace_id=default_ws.id if context.task_id else None,
                ),
                now=datetime.now(UTC),
            )
            return match.workspace_id if match else None

        app_control = default_app_control()
        focus_manager = FocusManager(app_control)
        # AX calls execute in the stable, signed helper bundle. Absence of the
        # local mode-0600 socket is typed unavailable; the daemon never falls
        # back to its unstable Python host identity.
        ax_helper = AXHelperClient()
        ax_permissions = AXPermissionService(trust_probe=ax_helper.is_trusted)
        ax_diagnostics = AXDiagnosticsStore()
        app.state.ax_helper = ax_helper
        app.state.ax_permissions = ax_permissions
        app.state.ax_diagnostics = ax_diagnostics
        ax_controller = AXController(
            AXHelperSemanticAXAdapter(ax_helper),
            ax_permissions,
            app.state.application_profiles,
            app_control=app_control,
            diagnostics=ax_diagnostics,
        )
        app.state.foreground = ForegroundContextBroker(
            app_control,
            workspace_matcher=match_workspace,
        )

        async def scope_provider() -> ResourceScope:
            scope = await permissions_store.effective_scope(default_ws.id)
            if "*" not in scope.domains:
                scope.domains.append("*")
            return scope

        def constraint_checker(task_id: str, tool_name: str) -> None:
            # No live follow-up state means there is no dynamic dialogue
            # constraint. Goal-derived constraints remain enforced by the
            # orchestrator itself.
            with suppress(DialogueExpired):
                app.state.dialogue.enforce_tool_constraints(
                    task_id,
                    tool_name,
                    datetime.now(UTC),
                )

        registry = build_registry()
        register_fs_tools(registry)  # real, scoped filesystem tools (slice 3)
        register_shell_tool(registry)  # restricted shell (slice 4)
        register_git_tools(registry)  # git workflow tools (slice 5)
        register_app_tools(registry, app_control)  # macOS app launch/focus/list (slice 6)
        register_browser_tools(
            registry,
            network_isolation=cfg.network_isolation,
        )  # scoped browser read (slice 7)
        register_semantic_ax_tools(registry, ax_controller)  # bounded semantic AX tools (5.4)
        register_browser_interaction_tools(
            registry,
            network_isolation=cfg.network_isolation,
        )  # interactive session (Phase 4 slice 4)
        register_research_tools(
            registry,
            inference_provider=app.state.inference_provider,
            browser_adapter=None,
        )  # deep research (Phase 2)

        # Planner selection (slice 8). Default "mock"; "claude" uses a
        # planning-only Anthropic call (needs ANTHROPIC_API_KEY). Plan output is
        # untrusted and validated by the same schema/registry/policy/scope gates.
        planner: PlannerAdapter
        if cfg.planner == "claude":
            planner = ClaudePlanner(registry, AnthropicPlannerClient())
        elif cfg.planner == "local":
            # Local constrained planner (Phase 5.1): the loopback model's plan
            # is rejected by the strict validator before any risk review, then
            # gated by every unchanged Phase 4 boundary. No cloud, ever.
            planner = LocalPlanner(
                registry,
                OllamaPlanClient(
                    model=cfg.inference_model,
                    endpoint=cfg.inference_endpoint,
                    isolation=cfg.network_isolation,
                ),
            )
        else:
            planner = DeterministicMockPlanner()
        app.state.orchestrator = Orchestrator(
            registry=registry,
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=cfg.approval_ttl_seconds),
            verifier=VerificationEngine(),
            recovery=RecoveryController(
                max_retries_per_step=cfg.max_retries_per_step,
                max_retries_per_task=cfg.max_retries_per_task,
            ),
            audit=audit_store,
            planner=planner,
            publish=publish,
            workspace=default_ws,
            enforcer=ScopeEnforcer(),
            scope_provider=scope_provider,
            focus_manager=focus_manager,
            focus_result_sink=app.state.focus_results.__setitem__,
            constraint_checker=constraint_checker,
        )
        app.state.voice_sessions = VoiceSessionRegistry(
            app.state.speech_recognition,
            retain_transcripts=cfg.voice_retain_transcripts,
            correction_window=timedelta(seconds=cfg.voice_correction_window_seconds),
            session_ttl=timedelta(seconds=cfg.voice_session_ttl_seconds),
            runtime=app.state.local_runtime,
            metrics=app.state.voice_metrics,
        )

        async def reap_abandoned_voice_sessions() -> None:
            interval = min(max(cfg.voice_session_ttl_seconds / 2, 1.0), 15.0)
            while True:
                await asyncio.sleep(interval)
                expired = app.state.voice_sessions.purge_expired()
                if expired:
                    log.info(
                        "voice_sessions_expired",
                        extra={"data": {"count": expired}},
                    )

        voice_janitor = asyncio.create_task(reap_abandoned_voice_sessions())
        app.state.global_stop = GlobalStopAuthority(
            sessions=app.state.voice_sessions,
            tts=app.state.speech_synthesis,
            orchestrator=app.state.orchestrator,
            metrics=app.state.voice_metrics,
        )
        db_grants = await permissions_store.list_grants()
        whitelisted_apps = {grant.value for grant in db_grants if grant.kind == "app" and grant.workspace_id == default_ws.id and not grant.revoked}
        whitelisted_apps.update(
            [
                "Google Chrome",
                "Chrome",
                "WhatsApp",
                "Finder",
                "Terminal",
                "VS Code",
                "TextEdit",
                "ChatGPT",
                "Safari",
                "Wispr Flow",
                "Claude",
                "QuickTime Player",
                "Telegram",
                "Code",
            ]
        )
        known_apps = {profile.display_name for profile in app.state.application_profiles.all()} | whitelisted_apps

        app.state.command_dispatcher = CommandDispatcher(
            orchestrator=app.state.orchestrator,
            stop=app.state.global_stop,
            speech=app.state.speech_synthesis,
            skills=app.state.skills,
            workspace=default_ws,
            known_apps=known_apps,
        )
        app.state.voice_commands = VoiceCommandService(
            sessions=app.state.voice_sessions,
            dispatcher=app.state.command_dispatcher,
            tts=app.state.speech_synthesis,
        )
        log.info("daemon_started", extra={"data": {"host": cfg.host, "port": cfg.port}})
        try:
            yield
        finally:
            voice_janitor.cancel()
            with suppress(asyncio.CancelledError):
                await voice_janitor
            app.state.voice_sessions.cancel_all()
            log.info("daemon_stopped")
            await engine.dispose()

    app = FastAPI(title="OmniMac Daemon", lifespan=lifespan)
    app.add_middleware(BearerAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(r"^(?:tauri://localhost|https?://(?:localhost|127\.0\.0\.1)(?::\d{1,5})?)$"),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(commands.router)
    app.include_router(tasks.router)
    app.include_router(ws.router)
    app.include_router(permissions.router)
    app.include_router(skills.router)
    app.include_router(settings_api.router)
    app.include_router(voice.router)
    app.include_router(intent.router)
    app.include_router(operational.router)
    app.include_router(runtime.router)
    return app
