from dataclasses import dataclass


@dataclass(frozen=True)
class GitStoreConfig:
    password: str
    request_timeout: int = 60

    def __post_init__(self) -> None:
        if not isinstance(self.password, str) or not self.password:
            raise ValueError("password must be a non-empty string.")
        if not isinstance(self.request_timeout, int) or self.request_timeout <= 0:
            raise ValueError("request_timeout must be a positive integer.")
