"""项目关系查询应用编排层。"""

from __future__ import annotations

from biz.schemas.project_relation import ProjectRelationPage, ProjectRelationQueryRequest
from infra.graph_db import TRSGraphClient
from service.project_relation import ProjectRelationService


class ProjectRelationApplication:
    def __init__(self, client: TRSGraphClient) -> None:
        self._service = ProjectRelationService(client)

    def query(self, body: ProjectRelationQueryRequest) -> ProjectRelationPage:
        return self._service.query(body)
