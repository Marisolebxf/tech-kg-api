from fastapi import HTTPException

from service.kg_construction import KGConstructionService


class KGConstructionApplication:
    def __init__(self) -> None:
        self._service = KGConstructionService()

    def list_modules(self) -> list[dict[str, object]]:
        return self._service.list_modules()

    def get_module(self, module_code: str) -> dict[str, object] | None:
        return self._service.get_module(module_code)

    def get_module_or_raise(self, module_code: str) -> dict[str, object]:
        module = self.get_module(module_code)
        if module is None:
            raise HTTPException(status_code=404, detail="Module not found")
        return module
