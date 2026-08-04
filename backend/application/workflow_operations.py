"""工作流控制面应用层。"""

from service.workflow_operations import WorkflowOperationsService, workflow_operations_service


class WorkflowOperationsApplication:
    def __init__(self, service: WorkflowOperationsService = workflow_operations_service) -> None:
        self.service = service


workflow_operations_application = WorkflowOperationsApplication()
