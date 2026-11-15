"""Orion application factory and ASGI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.agent.orchestrator import AgentOrchestrator
from app.api.middleware import SecurityHeadersMiddleware
from app.api.rate_limit import RateLimiter
from app.api.routes import build_router
from app.auth.identity import IdentityDirectory
from app.auth.providers import DevelopmentIdentityProvider
from app.auth.revocation import TokenRevocationService
from app.auth.tokens import TokenService
from app.authorization.policy import AuthorizationService
from app.config.settings import Settings, load_settings
from app.gateway.fake import FakeLLM
from app.gateway.gateway import (
    HostedModelProvider,
    ModelGateway,
    SelfHostedModelProvider,
)
from app.observability.audit import AuditRecorder
from app.observability.logging import SecurityLogger
from app.persistence.store import Store
from app.prompts.registry import PromptRegistry
from app.services.approvals import ApprovalService
from app.services.chat import ChatService
from app.services.documents import DocumentService
from app.tools.broker import ToolExecutionBroker
from app.tools.implementations import ToolImplementations
from app.tools.registry import build_default_registry


def _build_provider(settings: Settings, broker: ToolExecutionBroker):
    if settings.model_provider == "fake":
        return FakeLLM(broker)
    if settings.model_provider == "hosted":
        return HostedModelProvider()
    if settings.model_provider in {"self_hosted", "self-hosted"}:
        return SelfHostedModelProvider()
    raise RuntimeError(f"Unsupported model provider: {settings.model_provider}")


def create_app(
    database_path: Path | None = None,
    data_directory: Path | None = None,
    settings: Settings | None = None,
    llm=None,
) -> FastAPI:
    """Compose Orion as a modular monolith with dependency injection."""

    configured = settings or load_settings(
        data_directory=data_directory,
        database_path=database_path,
    )
    store = Store(configured.database_path, configured.data_directory)
    authorization = AuthorizationService()
    security_logger = SecurityLogger()
    audit = AuditRecorder(store, security_logger)
    directory = IdentityDirectory()
    revocation = TokenRevocationService(store)
    tokens = TokenService(configured, directory, revocation)
    identity_provider = DevelopmentIdentityProvider(configured, tokens, directory)
    tool_implementations = ToolImplementations(
        store, configured, authorization, audit
    )
    registry = build_default_registry(tool_implementations)
    broker = ToolExecutionBroker(
        registry, authorization, store, configured, audit, security_logger
    )
    provider = llm or _build_provider(configured, broker)
    prompts = PromptRegistry()
    gateway = ModelGateway(configured, provider, prompts, security_logger)
    orchestrator = AgentOrchestrator(gateway, configured, security_logger, store)
    chat_service = ChatService(orchestrator, audit)
    document_service = DocumentService(tool_implementations)
    approval_service = ApprovalService(broker, store, authorization)
    rate_limiter = RateLimiter()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    application = FastAPI(
        title="Orion Enterprise Knowledge Assistant",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.include_router(build_router())

    application.state.settings = configured
    application.state.store = store
    application.state.authorization = authorization
    application.state.security_logger = security_logger
    application.state.audit = audit
    application.state.identity_provider = identity_provider
    application.state.token_service = tokens
    application.state.revocation = revocation
    application.state.tool_implementations = tool_implementations
    application.state.registry = registry
    application.state.broker = broker
    application.state.llm = provider
    application.state.gateway = gateway
    application.state.orchestrator = orchestrator
    application.state.chat_service = chat_service
    application.state.document_service = document_service
    application.state.approval_service = approval_service
    application.state.rate_limiter = rate_limiter
    application.state.prompts = prompts
    return application


app = create_app()
