"""WorkflowJob 应用层薄封装（handler ↔ service）。"""

from __future__ import annotations

from service.workflow_jobs import WorkflowJobService, workflow_job_service


class WorkflowJobApplication:
    def __init__(self, service: WorkflowJobService) -> None:
        self.service = service


workflow_job_application = WorkflowJobApplication(workflow_job_service)
