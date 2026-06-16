from service.module_catalog import get_kg_construction_module, list_kg_construction_modules


class KGConstructionService:
    def list_modules(self) -> list[dict[str, object]]:
        return list_kg_construction_modules()

    def get_module(self, module_code: str) -> dict[str, object] | None:
        return get_kg_construction_module(module_code)
