"""프로필 Seed에 적용할 온톨로지 규칙. 전체 Personal Ontology의 초기 부분집합이다.

규칙 선언만 담당한다. 입력 변환과 KG 검증은 이 정의를 읽는 별도 로직에서 수행한다.
사용자가 제공하지 않은 학위·기간·졸업·재직 상태는 Seed 속성에 포함하지 않는다.
"""

from typing import Final, Literal

SEED_ONTOLOGY_VERSION: Final = "1.0"

SeedClassType = Literal["Person", "Education", "Experience", "Organization", "Channel"]
SeedRelationType = Literal["hasEducation", "hasExperience", "hasChannel", "atOrganization"]
SeedValueType = Literal["string", "uri"]

# (1) Entity별로 허용하는 Fact predicate와 value_type
# Channel.value는 이메일·전화번호면 string, GitHub 주소면 uri로 표현
SEED_PROPERTY_TYPES: Final[dict[SeedClassType, dict[str, tuple[SeedValueType, ...]]]] = {
    "Person": {"name": ("string",), "role": ("string",)},
    "Education": {"major": ("string",)},
    "Experience": {"role": ("string",), "unit": ("string",)},
    "Organization": {"name": ("string",), "type": ("string",)},
    "Channel": {"kind": ("string",), "value": ("string", "uri"), "scope": ("string",)},
}

# 값이 정해진 속성만 열거한다. 이름·전공·직책 등 자유 텍스트는 제한하지 않는다.
# Person.role은 서비스 유형, Experience.role은 실제 직책이므로 구분
SEED_PROPERTY_VALUES: Final[dict[tuple[SeedClassType, str], frozenset[str]]] = {
    ("Person", "role"): frozenset({"Student", "Professor", "Professional"}),
    ("Organization", "type"): frozenset({"company", "university"}),
    ("Channel", "kind"): frozenset({"email", "phone", "github"}),
    ("Channel", "scope"): frozenset({"personal", "work"}),
}

# (3) Relation별 허용 (출발 Entity 타입, 도착 Entity 타입)
# 여러 출발 타입을 동시에 요구하는 것이 아니라, 아래 쌍 중 하나를 허용
SEED_RELATION_PAIRS: Final[
    dict[SeedRelationType, frozenset[tuple[SeedClassType, SeedClassType]]]
] = {
    "hasEducation": frozenset({("Person", "Education")}),
    "hasExperience": frozenset({("Person", "Experience")}),
    "hasChannel": frozenset({("Person", "Channel")}),
    "atOrganization": frozenset({("Education", "Organization"), ("Experience", "Organization")}),
}
