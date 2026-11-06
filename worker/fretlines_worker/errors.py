class AnalysisError(Exception):
    """Ошибка разбора с человеческим текстом для интерфейса (SPEC §2.6)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
