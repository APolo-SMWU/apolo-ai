"""Backend가 저장하고 서명한 PDF·Word 원본 참조. 임의 다운로드 주소는 받지 않는다."""

import re
from pathlib import PurePath
from typing import Literal, Self
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_S3_HOST = re.compile(r"(?:[a-z0-9][a-z0-9.-]*\.)?s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com\Z")


class SourceAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    mime_type: Literal[
        "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ] = Field(alias="mimeType")
    source_url: str = Field(
        alias="sourceUrl",
        max_length=1024,
        pattern=r"^portfolios/[A-Za-z0-9-]+/attachments/[A-Za-z0-9-]+\.(?:pdf|docx)$",
    )
    download_url: str = Field(alias="downloadUrl", max_length=8192, repr=False)

    @model_validator(mode="after")
    def require_stored_document(self) -> Self:
        extension = ".pdf" if self.mime_type == "application/pdf" else ".docx"
        if PurePath(self.file_name).suffix.lower() != extension or not self.source_url.endswith(
            extension
        ):
            raise ValueError("첨부파일 이름·종류·저장 위치가 일치해야 합니다.")
        url = urlsplit(self.download_url)
        if (
            url.scheme != "https"
            or not _S3_HOST.fullmatch(url.hostname or "")
            or url.port not in {None, 443}
            or url.username
            or url.password
            or url.fragment
            or not unquote(url.path).endswith("/" + self.source_url)
        ):
            raise ValueError("첨부파일은 저장된 S3 원본 주소만 사용할 수 있습니다.")
        return self
