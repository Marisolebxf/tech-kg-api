from service.module_catalog import get_kg_construction_module


class KGModuleScaffoldService:
    module_code: str

    def describe(self) -> dict[str, object]:
        module = get_kg_construction_module(self.module_code)
        if module is None:
            raise ValueError(f"Unknown module code: {self.module_code}")
        return module
