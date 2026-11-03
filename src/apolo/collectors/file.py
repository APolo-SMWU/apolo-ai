"""비공개 첨부를 크기 제한 안에서 내려받아 기존 파일 수집기에 전달한다."""

import asyncio

import httpx

from apolo.contracts.attachment import MAX_ATTACHMENT_BYTES, SourceAttachment
from apolo.contracts.source import CollectedSource


class FileCollectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def collect_file_source(
    attachment: SourceAttachment, *, client: httpx.AsyncClient
) -> CollectedSource:
    try:
        async with client.stream(
            "GET", attachment.download_url, follow_redirects=False, timeout=30.0
        ) as response:
            if response.status_code != 200:
                raise FileCollectionError(
                    "file_download_failed", "첨부파일 원본을 가져오지 못했습니다."
                )
            length = response.headers.get("content-length")
            if length and int(length) > MAX_ATTACHMENT_BYTES:
                raise FileCollectionError("too_large", "첨부파일은 10MB 이하만 읽을 수 있습니다.")
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_ATTACHMENT_BYTES:
                    raise FileCollectionError(
                        "too_large", "첨부파일은 10MB 이하만 읽을 수 있습니다."
                    )
    except FileCollectionError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise FileCollectionError(
            "file_download_failed", "첨부파일 원본을 가져오지 못했습니다."
        ) from error

    # 파일을 쓰지 않는 생성 요청에서는 파서 의존성을 불러오지 않는다.
    if attachment.mime_type == "application/pdf":
        from apolo.collectors.pdf import collect_pdf_source as collector
    else:
        from apolo.collectors.docx import collect_docx_source as collector
    return await asyncio.to_thread(
        collector, bytes(data), file_name=attachment.file_name, source_url=attachment.source_url
    )
