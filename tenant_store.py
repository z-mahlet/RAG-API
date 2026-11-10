import json
import os
from typing import Optional
from pydantic import BaseModel, Field

DATA_FILE = "tenants.json"


class TenantConfig(BaseModel):
    tenant_id: str
    bot_name: str = Field(default="Knowledge Assistant")
    theme_color: str = Field(default="#2563eb")
    greeting_message: str = Field(
        default="Hello! How can I assist you today?"
    )
    fallback_message: str = Field(
        default="I am sorry, but I do not have enough information to answer that question."
    )
    farewell_message: str = Field(
        default="Thank you for chatting with us. Have a great day!"
    )
    system_persona: str = Field(
        default="You are a helpful, professional AI assistant for our application. Answer queries politely and accurately."
    )
    # --- NEW FIELDS ---
    allow_general_chat: bool = Field(
        default=True,
        description="If True, answers using persona and general knowledge when no docs exist or match. If False, strictly enforces fallback."
    )
    app_description: str = Field(
        default="This is an online web application providing on-demand services to users.",
        description="Overview of what the host application or website does so the bot can explain it."
    )
    max_distance_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Cosine distance cutoff. Matches farther than this trigger fallback or general knowledge."
    )

class TenantStore:
    def __init__(self, storage_path: str = DATA_FILE):
        self.storage_path = storage_path
        self._ensure_storage()

    def _ensure_storage(self):
        if not os.path.exists(self.storage_path):
            # Seed with a default demo tenant
            default_tenant = TenantConfig(
                tenant_id="default",
                bot_name="Acme Knowledge Bot",
                theme_color="#059669",
                greeting_message="Welcome to Acme Corp! Ask me anything about our policies.",
                fallback_message="That topic is not covered in Acme's official documentation.",
                system_persona="You are a friendly internal HR assistant at Acme Corp. Use a polite, supportive, and clear tone."
            )
            self.save(default_tenant)

    def _load_all(self) -> dict[str, dict]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def get(self, tenant_id: str) -> TenantConfig:
        data = self._load_all()
        if tenant_id in data:
            return TenantConfig(**data[tenant_id])
        # Return fallback configuration if tenant does not yet have custom settings
        return TenantConfig(tenant_id=tenant_id)

    def save(self, config: TenantConfig) -> TenantConfig:
        data = self._load_all()
        data[config.tenant_id] = config.model_dump()
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return config


# Singleton tenant store instance
tenant_store = TenantStore()