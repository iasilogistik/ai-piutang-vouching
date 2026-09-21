from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    supabase_publishable_key: str | None = None
    supabase_storage_bucket: str = "audit-documents"
    google_drive_api_key: str | None = None
    auth_required: bool = False
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def use_supabase_storage(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)


settings = Settings()
