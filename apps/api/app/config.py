import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "PayPal AI Dispute Investigator"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./paypal_disputes.db")
    
    # PayPal Sandbox Configuration
    PAYPAL_ENVIRONMENT: str = os.getenv("PAYPAL_ENVIRONMENT", "sandbox")
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_BASE_URL: str = os.getenv(
        "PAYPAL_BASE_URL", 
        "https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_ENVIRONMENT", "sandbox") == "sandbox" else "https://api-m.paypal.com"
    )
    
    # AI Engine Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    NBE_POLICY_TYPE: str = os.getenv("NBE_POLICY_TYPE", "heuristic")  # "heuristic" or "llm"
    
    # Security & Storage
    MAX_UPLOAD_SIZE_MB: int = 10
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    
    # Demo and Synthetic Flags
    ENABLE_SYNTHETIC_SCENARIOS: bool = True


settings = Settings()
