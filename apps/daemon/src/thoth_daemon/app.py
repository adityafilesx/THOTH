from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI

from thoth_daemon.api import (
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
from thoth_daemon.api import settings as settings_api
from thoth_daemon.api.middleware import BearerAuthMiddleware
from thoth_daemon.audit.store import AuditStore
from thoth_daemon.config import Settings
from thoth_daemon.core.application_profiles import build_default_application_profiles
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.ax_controller import AXController
from thoth_daemon.core.ax_diagnostics import AXDiagnosticsStore
from thoth_daemon.core.claude_planner import AnthropicPlannerClient, ClaudePlanner
from thoth_daemon.core.dialogue import DialogueExpired, OperationalDialogueStore
from thoth_daemon.core.focus import FocusManager
from thoth_daemon.core.foreground import ForegroundContext, ForegroundContextBroker
from thoth_daemon.core.local_plan_client import OllamaPlanClient
from thoth_daemon.core.local_planner import LocalPlanner
from thoth_daemon.core.local_runtime import (
    InferenceRuntimeDriver,
    LocalAIRuntimeManager,
    RuntimeComponent,
    RuntimeRegistration,
    SpeechRecognitionRuntimeDriver,
    SpeechSynthesisRuntimeDriver,
)
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import DeterministicMockPlanner, PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.runtime_status import LocalRuntimeMonitor
from thoth_daemon.core.scope import ScopeEnforcer
from thoth_daemon.core.skill_engine import seed_builtin_skills
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.core.workspace_matching import (
    WorkspaceAssociationProfile,
    WorkspaceEvidence,
    WorkspaceMatcher,
)
from thoth_daemon.events.bus import EventBus
from thoth_daemon.inference import (
    DeterministicInferenceProvider,
    InferenceProvider,
    LlamaCppInferenceProvider,
    MLXInferenceProvider,
)
from thoth_daemon.logging_setup import configure_logging, get_logger
from thoth_daemon.macos.app_control import default_app_control
from thoth_daemon.macos.ax_helper import AXHelperClient, AXHelperSemanticAXAdapter
from thoth_daemon.macos.ax_permission import AXPermissionService
from thoth_daemon.schemas import ResourceScope, WorkspaceProfile
from thoth_daemon.security.auth import mint_token, write_token_file
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.storage.permissions import PermissionStore
from thoth_daemon.storage.skills import SkillStore
from thoth_daemon.tools.app_tools import register_app_tools
from thoth_daemon.tools.browser_interaction_tools import register_browser_interaction_tools
from thoth_daemon.tools.browser_tools import register_browser_tools
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.git_tools import register_git_tools
from thoth_daemon.tools.mock_tools import build_registry
from thoth_daemon.tools.semantic_ax_tools import register_semantic_ax_tools
from thoth_daemon.tools.shell_tool import register_shell_tool
from thoth_daemon.voice.service import VoiceCommandService, VoiceSessionRegistry
from thoth_daemon.voice.stop import GlobalStopAuthority
from thoth_daemon.voice.stt import (
    SpeechRecognitionSTTAdapter,
    WhisperCppSpeechRecognitionProvider,
)
from thoth_daemon.voice.tts import MacOSSpeechSynthesisProvider, SpeechSynthesisService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(cfg.log_dir, cfg.log_level)
        log = get_logger("thoth.app")
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
        if existing:
            default_ws = existing[0]
        else:
            default_ws = WorkspaceProfile(
                name="default",
                root_path=cfg.trusted_workspaces[0] if cfg.trusted_workspaces else "",
                trusted=bool(cfg.trusted_workspaces),
            )
            await permissions_store.upsert_workspace(default_ws)
        app.state.permissions = permissions_store
        app.state.skills = SkillStore(session_factory)
        await seed_builtin_skills(app.state.skills)  # idempotent (Phase 4 slice 5)

        app.state.speech_synthesis_provider = MacOSSpeechSynthesisProvider()
        app.state.speech_synthesis = SpeechSynthesisService(app.state.speech_synthesis_provider)
        app.state.speech_recognition = WhisperCppSpeechRecognitionProvider(
            executable=cfg.whisper_executable,
            model_path=cfg.whisper_model_path,
            language=cfg.whisper_language,
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
                integrity_verified=None,
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
                    approved_workspace_path=(
                        default_ws.root_path if context.task_id and default_ws.root_path else None
                    ),
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
            return await permissions_store.effective_scope(default_ws.id)

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
        register_browser_tools(registry)  # scoped browser read (slice 7)
        register_semantic_ax_tools(registry, ax_controller)  # bounded semantic AX tools (5.4)
        register_browser_interaction_tools(registry)  # interactive session (Phase 4 slice 4)

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
            runtime=app.state.local_runtime,
        )
        app.state.global_stop = GlobalStopAuthority(
            sessions=app.state.voice_sessions,
            tts=app.state.speech_synthesis,
            orchestrator=app.state.orchestrator,
        )
        app.state.voice_commands = VoiceCommandService(
            sessions=app.state.voice_sessions,
            stop=app.state.global_stop,
            orchestrator=app.state.orchestrator,
            tts=app.state.speech_synthesis,
        )
        log.info("daemon_started", extra={"data": {"host": cfg.host, "port": cfg.port}})
        yield
        log.info("daemon_stopped")
        await engine.dispose()

    app = FastAPI(title="THOTH Daemon", lifespan=lifespan)
    app.add_middleware(BearerAuthMiddleware)
    app.include_router(health.router)
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
