"""APolo 공통 Personal Ontology 규칙
규칙 선언만 담당한다. 외부 추출 결과의 검증은 이 정의를 읽는 별도 로직에서 수행한다.
프로필 Seed 규칙(ontology/seed.py)은 이 규칙의 부분집합이다.
"""

from typing import Final, Literal

ONTOLOGY_VERSION: Final = "2.0"

ClassType = Literal[
    "Person",
    "Education",
    "Experience",
    "Activity",
    "Work",
    "Credential",
    "Skill",
    "Organization",
    "Channel",
]
RelationType = Literal[
    "hasEducation",
    "hasExperience",
    "participatedIn",
    "holds",
    "hasSkill",
    "hasChannel",
    "atOrganization",
    "usesSkill",
    "partOf",
]
ValueType = Literal["string", "uri", "date", "boolean"]

# (1) Class별 허용 Fact predicate와 value_type. 노션 Ontology Schema에 결정 사항을 반영했다.
# date는 ISO 형식 문자열(YYYY, YYYY-MM, YYYY-MM-DD)이다.
# 진행 중이면 end를 두지 않고 isCurrent=true로 표현한다. 'Present'를 값으로 저장하지 않는다.
PROPERTY_TYPES: Final[dict[ClassType, dict[str, tuple[ValueType, ...]]]] = {
    "Person": {
        "name": ("string",),
        "role": ("string",),
        "interests": ("string",),
    },
    "Education": {
        "major": ("string",),
        "degree": ("string",),
        "start": ("date",),
        "end": ("date",),
        "isCurrent": ("boolean",),
    },
    "Experience": {
        "role": ("string",),
        "department": ("string",),
        "kind": ("string",),
        "start": ("date",),
        "end": ("date",),
        "isCurrent": ("boolean",),
    },
    "Activity": {
        "name": ("string",),
        "role": ("string",),
        "kind": ("string",),
        "start": ("date",),
        "end": ("date",),
        "isCurrent": ("boolean",),
    },
    "Work": {
        "title": ("string",),
        "kind": ("string",),
        "role": ("string",),
        "start": ("date",),
        "end": ("date",),
        "url": ("uri",),
    },
    "Credential": {
        "title": ("string",),
        "kind": ("string",),
        "issuerName": ("string",),
        "date": ("date",),
        "grade": ("string",),
    },
    "Skill": {
        "name": ("string",),
        "category": ("string",),
    },
    "Organization": {
        "name": ("string",),
        "type": ("string",),
        "homepage": ("uri",),
    },
    "Channel": {
        "kind": ("string",),
        "value": ("string", "uri"),
        "scope": ("string",),
    },
}

# (2) 값이 정해진 속성만 열거한다. 코드가 이 값으로 분기하거나 비교하는 속성이다.
# 목록 밖 값은 비슷한 값으로 추측해 바꾸지 않는다. 검증에서 해당 Fact만 제외한다.
PROPERTY_VALUES: Final[dict[tuple[ClassType, str], frozenset[str]]] = {
    ("Person", "role"): frozenset({"Student", "Professor", "Professional"}),
    ("Experience", "kind"): frozenset({"fulltime", "contract", "intern", "research"}),
    ("Activity", "kind"): frozenset({"club", "volunteer", "program", "talk"}),
    ("Work", "kind"): frozenset({"project", "publication", "opensource"}),
    ("Credential", "kind"): frozenset({"award", "certification"}),
    ("Organization", "type"): frozenset(
        {"company", "university", "club", "institution", "github_org"}
    ),
    ("Channel", "kind"): frozenset({"email", "phone", "github"}),
    ("Channel", "scope"): frozenset({"personal", "work"}),
}

# (3) 한 Entity가 같은 predicate의 Fact를 여러 개 가질 수 있는 속성. 나머지는 값이 하나다.
MULTI_VALUED_PROPERTIES: Final[frozenset[tuple[ClassType, str]]] = frozenset(
    {
        ("Education", "major"),
        ("Work", "url"),
        ("Person", "interests"),
        ("Skill", "category"),
    }
)

# (4) Relation별 허용 (출발 Class, 도착 Class). 여러 쌍 중 하나를 만족하면 된다.
RELATION_PAIRS: Final[dict[RelationType, frozenset[tuple[ClassType, ClassType]]]] = {
    "hasEducation": frozenset({("Person", "Education")}),
    "hasExperience": frozenset({("Person", "Experience")}),
    "participatedIn": frozenset({("Person", "Activity"), ("Person", "Work")}),
    "holds": frozenset({("Person", "Credential")}),
    "hasSkill": frozenset({("Person", "Skill")}),
    "hasChannel": frozenset({("Person", "Channel")}),
    "atOrganization": frozenset(
        {
            ("Education", "Organization"),
            ("Experience", "Organization"),
            ("Activity", "Organization"),
            ("Work", "Organization"),
        }
    ),
    "usesSkill": frozenset({("Work", "Skill"), ("Experience", "Skill")}),
    # 기간이 겹친다는 이유만으로 연결하지 않는다. 출처나 충분한 맥락 근거가 있어야 한다.
    "partOf": frozenset({("Work", "Experience")}),
}
