"""HTTP DTO validation; domain/application classes do not import Pydantic."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from codebase_analysis.models.task import BuildRequest


class SubmitAnalysis(BaseModel):
    """Jenkins sends identity only; arbitrary artifact URLs are not accepted."""

    model_config = ConfigDict(extra='forbid', strict=True)
    provider: Literal['github', 'gitlab']
    repository: Annotated[str, Field(min_length=1, max_length=256)]
    number: Annotated[int, Field(gt=0)]
    head_sha: Annotated[str, Field(pattern=r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')]
    job_name: Annotated[str, Field(pattern=r'^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$', max_length=256)]
    build_number: Annotated[int, Field(gt=0)]

    def to_domain(self) -> BuildRequest:
        return BuildRequest(**self.model_dump())
