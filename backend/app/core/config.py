from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Eltel Pole Prototype"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000

    use_azure_di: bool = False
    azure_di_endpoint: str = ""
    azure_di_key: str = ""

    use_azure_openai: bool = False
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()