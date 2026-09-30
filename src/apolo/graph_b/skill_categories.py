"""Skills 블록에서 사용할 기술명 기반 표시 카테고리 정책"""

import unicodedata

UNCATEGORIZED_SKILL_CATEGORY = "기타"

PROGRAMMING_LANGUAGES = "프로그래밍 언어"
FRONTEND_MOBILE = "프론트엔드·모바일"
BACKEND_API = "백엔드·API"
DATABASES = "데이터베이스"
AI_ML_TOOLS = "AI·ML 도구"
DATA_ANALYTICS = "데이터·시각화"
CLOUD_INFRASTRUCTURE = "클라우드·인프라"
DEVELOPER_TOOLS = "개발·자동화 도구"

SKILL_CATEGORIES = (
    PROGRAMMING_LANGUAGES,
    FRONTEND_MOBILE,
    BACKEND_API,
    DATABASES,
    AI_ML_TOOLS,
    DATA_ANALYTICS,
    CLOUD_INFRASTRUCTURE,
    DEVELOPER_TOOLS,
    UNCATEGORIZED_SKILL_CATEGORY,
)


_SKILLS_BY_CATEGORY = {
    PROGRAMMING_LANGUAGES: {
        "python", "typescript", "javascript", "sql", "r", "java", "kotlin",
        "swift", "go", "golang", "rust", "c", "c++", "c#", "php", "ruby",
        "scala", "dart", "bash", "powershell",
    },
    FRONTEND_MOBILE: {
        "html/css", "html", "css", "react", "next.js", "react native", "vue",
        "vue.js", "angular", "svelte", "tailwind css", "android", "ios", "flutter",
    },
    BACKEND_API: {
        "fastapi", "rest", "flask", "django", "spring", "spring boot", "node.js",
        "express", "express.js", "nestjs", "graphql", "swagger ui", "postman",
    },
    DATABASES: {
        "postgresql", "postgres", "mysql", "mariadb", "mongodb", "redis", "sqlite",
        "supabase", "dynamodb", "elasticsearch",
    },
    AI_ML_TOOLS: {
        "pytorch", "tensorflow", "transformers", "scikit-learn", "sklearn",
        "langchain", "langgraph", "faiss", "ragas", "bertopic", "keybert",
        "wordnet", "hugging face", "huggingface", "openai api", "langsmith",
    },
    DATA_ANALYTICS: {
        "tableau", "power bi", "pandas", "numpy", "matplotlib", "seaborn",
        "looker", "excel",
    },
    CLOUD_INFRASTRUCTURE: {
        "azure", "microsoft azure paas", "azure paas", "azure container instances",
        "azure ai search", "aws", "amazon web services", "gcp", "google cloud",
        "docker", "kubernetes", "terraform", "vercel",
    },
    DEVELOPER_TOOLS: {
        "github", "git", "figma", "storybook", "n8n", "linux", "jira",
        "vscode", "visual studio code", "notion",
    },
}

_CATEGORY_BY_SKILL_NAME = {
    unicodedata.normalize("NFKC", name).casefold().strip(): category
    for category, names in _SKILLS_BY_CATEGORY.items()
    for name in names
}


def skill_display_category(name: str) -> str:
    """KG에 저장된 Skill 이름을 Skills 블록의 표시 카테고리로 분류한다."""

    normalized = " ".join(unicodedata.normalize("NFKC", name).casefold().split())
    category = _CATEGORY_BY_SKILL_NAME.get(normalized)
    if category is not None:
        return category

    # Azure 제품·서비스 이름은 개별 Skill로 유지하고 같은 카테고리에 배치한다.
    if normalized.startswith(("azure ", "microsoft azure ")):
        return CLOUD_INFRASTRUCTURE

    return UNCATEGORIZED_SKILL_CATEGORY
