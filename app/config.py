from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    jwt_secret: str
    jwt_expires_hours: int
    timezone: str

    @classmethod
    def from_env(cls) -> "Config":
        secret = os.getenv("JWT_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET must be set in .env and be at least 32 characters long")
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            jwt_secret=secret,
            jwt_expires_hours=int(os.getenv("JWT_EXPIRES_HOURS", "8")),
            timezone=os.getenv("APP_TIMEZONE", "America/Chihuahua"),
        )

    @property
    def db_target(self) -> str:
        host = self.neo4j_uri.split("://")[-1]
        return f"{host}/{self.neo4j_database}"
