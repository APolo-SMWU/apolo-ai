"""Awards·Certification 블록 생성 규칙"""

from textwrap import dedent

CREDENTIALS_PROMPT = dedent(
    """
    awards와 certification 블록은 Credential Entity만 사용한다.
    Credential의 kind가 award이면 awards 블록으로 출력한다.
    Credential의 kind가 certification이면 certification 블록으로 출력한다.
    kind가 award 또는 certification으로 확인되지 않으면 해당 item을 만들지 않는다.
    awards와 certification의 entityId는 제공된 Credential Entity의 id를 그대로 사용한다.
    title은 Credential의 title fact를 그대로 사용한다.
    issuer는 Credential의 issuerName fact가 있을 때만 사용하고 없으면 null로 둔다.
    date는 Credential의 date fact가 있을 때만 YYYY 또는 YYYY.MM으로 변환하고 없으면 null로 둔다.
    awards의 description은 source evidence와 KG 사실을 근거로 짧게 요약한다.
    근거가 없으면 null로 둔다.
    certification의 grade는 Credential의 grade fact가 있을 때만 사용하고 없으면 null로 둔다.
    근거 없는 수상 내용·등급·점수·기관·날짜를 추론하거나 생성하지 않는다.
    awards item에는 certification 전용 grade 필드를 넣지 않는다.
    certification item에는 awards 전용 description 필드를 넣지 않는다.
    같은 Credential Entity는 한 번만 반환하고 빈 블록은 반환하지 않는다.
    """
).strip()
