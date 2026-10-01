"""Skills 블록의 표준 카테고리와 이름 정규화 규칙."""

import unicodedata
from collections.abc import Iterable

UNCATEGORIZED_SKILL_CATEGORY = "기타"

# Notion의 'Skills 카테고리 및 스킬 목록'. 이 사전은 분류용 참고 목록이며
# 출력 가능한 기술의 화이트리스트가 아니다.
_CATEGORY_SKILLS_RAW = {
    "언어": """
        JavaScript, TypeScript, Python, Java, Kotlin, Swift, Dart, Go, Rust, C, C++,
        C#, PHP, Ruby, R, Scala, Julia, SQL, Bash, PowerShell
    """,
    "웹 마크업 & 스타일링": """
        HTML, CSS, Sass, Less, Tailwind CSS, CSS Modules, Styled Components,
        Emotion, Bootstrap
    """,
    "프론트엔드": """
        React, Next.js, Vue.js, Nuxt, Angular, Svelte, SvelteKit, Astro, Remix, jQuery
    """,
    "UI 컴포넌트": """
        MUI, Ant Design, Chakra UI, shadcn/ui, Radix UI, Headless UI, Mantine,
        Vuetify, Element Plus
    """,
    "백엔드": """
        Node.js, Deno, Bun, Express, NestJS, Fastify, Hono, Spring, Spring Boot,
        Django, Flask, FastAPI, Django REST Framework, ASP.NET Core, Laravel,
        Symfony, Ruby on Rails, Gin, Echo, Fiber
    """,
    "모바일": """
        Android SDK, Jetpack Compose, Android Views, SwiftUI, UIKit, Flutter,
        React Native, Expo, Kotlin Multiplatform, .NET MAUI, Ionic, Capacitor
    """,
    "상태 관리": """
        Redux, Redux Toolkit, Zustand, Jotai, Recoil, MobX, XState, Pinia, Vuex,
        NgRx, Riverpod, Provider, BLoC, GetX
    """,
    "서버 상태 & 데이터 패칭": """
        TanStack Query, SWR, Apollo Client, RTK Query
    """,
    "API & 통신": """
        REST API, GraphQL, gRPC, WebSocket, SSE, tRPC, OpenAPI, Swagger, Axios,
        Retrofit, OkHttp, Alamofire, Dio
    """,
    "데이터베이스": """
        PostgreSQL, MySQL, MariaDB, SQLite, Oracle Database, SQL Server, MongoDB,
        DynamoDB, Cassandra, CouchDB, Neo4j, Cloud Firestore,
        Firebase Realtime Database
    """,
    "ORM & 데이터 접근": """
        Prisma, TypeORM, Sequelize, Drizzle ORM, Hibernate, JPA, Spring Data JPA,
        MyBatis, SQLAlchemy, Django ORM, Entity Framework Core, Mongoose, Room,
        Core Data
    """,
    "캐시 & 검색": """
        Redis, Memcached, Elasticsearch, OpenSearch, Apache Solr, Meilisearch,
        Algolia
    """,
    "메시징 & 이벤트 스트리밍": """
        Apache Kafka, RabbitMQ, Apache Pulsar, NATS, Amazon SQS, Amazon SNS,
        Google Cloud Pub/Sub, Amazon Kinesis
    """,
    "인증 & 보안": """
        OAuth 2.0, OpenID Connect, JWT, SAML, WebAuthn, Spring Security, Passport.js,
        Auth.js, Keycloak, Auth0, Firebase Authentication, OWASP, Vault
    """,
    "아키텍처 & 설계": """
        MVC, MVP, MVVM, MVI, Clean Architecture, Hexagonal Architecture,
        Layered Architecture, DDD, Microservices, Event-Driven Architecture, CQRS,
        Event Sourcing, Serverless Architecture, Design Patterns
    """,
    "빌드 & 패키지 도구": """
        Vite, Webpack, Rollup, Parcel, esbuild, SWC, Babel, Turbopack, npm, Yarn,
        pnpm, Maven, Gradle, Poetry, uv, pip, Bundler, NuGet, Turborepo, Nx
    """,
    "개발 & 자동화 도구": """
        Git, GitHub CLI, Make, Task, pre-commit, Husky, lint-staged, Plop, Hygen,
        n8n, Zapier, Make.com
    """,
    "CI/CD": """
        GitHub Actions, GitLab CI/CD, Jenkins, CircleCI, Travis CI, Azure Pipelines,
        Argo CD, Tekton, AWS CodePipeline, Bitrise, Codemagic, Fastlane
    """,
    "컨테이너 & 인프라 자동화": """
        Docker, Docker Compose, Podman, Kubernetes, Helm, Kustomize, Terraform,
        OpenTofu, Pulumi, AWS CloudFormation, AWS CDK, Ansible, Packer
    """,
    "클라우드 & 배포": """
        AWS, Google Cloud, Microsoft Azure, Naver Cloud, Vercel, Netlify,
        Cloudflare Workers, Cloudflare Pages, Render, Railway, Fly.io, Heroku,
        Firebase Hosting, Amazon EC2, Amazon ECS, Amazon EKS, AWS Lambda,
        Google Cloud Run
    """,
    "스토리지 & CDN": """
        Amazon S3, Google Cloud Storage, Azure Blob Storage, Cloudflare R2,
        Amazon CloudFront, Cloudflare CDN, Cloudinary
    """,
    "운영체제 & 서버": """
        Linux, Ubuntu, Debian, RHEL, Alpine Linux, Windows Server, Nginx,
        Apache HTTP Server, Caddy, IIS, Apache Tomcat
    """,
    "네트워크": """
        HTTP, HTTPS, TCP/IP, DNS, TLS, VPN, VPC, Load Balancing, Reverse Proxy
    """,
    "테스트 & 품질": """
        Jest, Vitest, Testing Library, Mocha, Chai, Jasmine, JUnit, Mockito, Pytest,
        unittest, PHPUnit, RSpec, xUnit, NUnit, Playwright, Cypress, Selenium,
        Puppeteer, Appium, Espresso, XCTest, Detox, Maestro, Postman, Newman,
        REST Assured, Supertest, k6, JMeter, Locust, ESLint, Prettier, Biome, Ruff,
        mypy, SonarQube
    """,
    "모니터링 & 관측": """
        Prometheus, Grafana, Datadog, New Relic, Sentry, OpenTelemetry, Jaeger,
        Zipkin, Amazon CloudWatch, Elastic Stack, Loki, Fluentd, Fluent Bit
    """,
    "데이터 수집 & 처리": """
        pandas, NumPy, Polars, SciPy, tidyverse, Apache Spark, Apache Hadoop,
        Apache Flink, Apache Beam, Dask, Scrapy, Beautiful Soup, Selenium
    """,
    "데이터 파이프라인": """
        Apache Airflow, Dagster, Prefect, dbt, Airbyte, Fivetran, Apache NiFi,
        Luigi, AWS Glue
    """,
    "데이터 웨어하우스 & 레이크하우스": """
        BigQuery, Snowflake, Amazon Redshift, Azure Synapse Analytics, Databricks,
        DuckDB, ClickHouse, Trino, Apache Hive, Delta Lake, Apache Iceberg,
        Apache Hudi
    """,
    "데이터 분석 & BI": """
        Excel, Google Sheets, Power Query, Power Pivot, Tableau, Power BI, Looker,
        Looker Studio, Metabase, Apache Superset, GA4, Amplitude, Mixpanel
    """,
    "데이터 시각화": """
        Matplotlib, Seaborn, Plotly, Bokeh, Altair, ggplot2, D3.js, Chart.js,
        Recharts, Apache ECharts, Highcharts
    """,
    "통계 & 실험": """
        기술통계, 추론통계, 가설검정, 회귀분석, 분산분석, 베이지안 분석,
        시계열 분석, 생존분석, 인과추론, A/B Testing, 코호트 분석, 퍼널 분석
    """,
    "머신러닝 & 딥러닝": """
        scikit-learn, XGBoost, LightGBM, CatBoost, PyTorch, TensorFlow, Keras, JAX,
        Hugging Face Transformers, PyTorch Lightning
    """,
    "자연어 처리 & 컴퓨터 비전": """
        spaCy, NLTK, Gensim, Sentence Transformers, KoNLPy, OpenCV, torchvision,
        Detectron2, Ultralytics YOLO, Tesseract
    """,
    "생성형 AI & LLM": """
        OpenAI API, Anthropic API, Gemini API, LangChain, LangGraph, LlamaIndex,
        Semantic Kernel, DSPy, Prompt Engineering, RAG, Tool Calling, Fine-tuning,
        LoRA, PEFT
    """,
    "벡터 검색 & 데이터베이스": """
        FAISS, pgvector, Pinecone, Weaviate, Milvus, Chroma, Qdrant, Annoy
    """,
    "지식 그래프 & 온톨로지": """
        RDF, RDFS, OWL, SPARQL, SHACL, JSON-LD, Protégé, Apache Jena, RDFLib,
        GraphDB, Stardog
    """,
    "MLOps & 모델 서빙": """
        MLflow, Weights & Biases, DVC, Kubeflow, TensorBoard, Optuna, Ray Tune,
        BentoML, KServe, Seldon Core, NVIDIA Triton, TorchServe,
        TensorFlow Serving, ONNX Runtime, vLLM, Amazon SageMaker, Vertex AI,
        Evidently
    """,
    "디자인 & 프로토타이핑": """
        Figma, Sketch, Adobe XD, Framer, ProtoPie, Photoshop, Illustrator,
        After Effects, Lottie
    """,
    "문서화 & 협업": """
        GitHub, GitLab, Bitbucket, Notion, Confluence, Jira, Linear, Trello, Slack,
        Microsoft Teams, Miro, FigJam, Storybook, Docusaurus, MkDocs
    """,
    "게임 & 실시간 그래픽": """
        Unity, Unreal Engine, Godot, Cocos Creator, Three.js, Babylon.js, WebGL,
        WebGPU, OpenGL, Vulkan, DirectX
    """,
    "임베디드 & IoT": """
        Arduino, ESP-IDF, STM32 HAL, FreeRTOS, Zephyr, Embedded Linux, ROS, ROS 2,
        MQTT, PlatformIO
    """,
}


def _normalize_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


_CATEGORY_SKILLS = {
    category: tuple(skill.strip() for skill in names.split(",") if skill.strip())
    for category, names in _CATEGORY_SKILLS_RAW.items()
}
SKILL_CATEGORIES = (*_CATEGORY_SKILLS, UNCATEGORIZED_SKILL_CATEGORY)
SKILL_CATEGORY_CATALOG = "\n".join(
    f"- {category}: {', '.join(skills)}" for category, skills in _CATEGORY_SKILLS.items()
)

_CANONICAL_NAME_BY_NORMALIZED = {}
_CATEGORIES_BY_NORMALIZED_NAME = {}
for _category, _names in _CATEGORY_SKILLS.items():
    for _name in _names:
        _normalized = _normalize_name(_name)
        _CANONICAL_NAME_BY_NORMALIZED.setdefault(_normalized, _name)
        _CATEGORIES_BY_NORMALIZED_NAME.setdefault(_normalized, set()).add(_category)

# 표기만 다른 동의어를 합칠 때 쓰며, 관련 기술을 하나로 묶는 데 사용하지 않는다.
_NAME_ALIASES = {
    "reactjs": "React",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "postgres": "PostgreSQL",
    "sklearn": "scikit-learn",
    "hugging face transformers": "Hugging Face Transformers",
}

_CATEGORIES_BY_NORMALIZED_NAME.setdefault("azure", set()).add("클라우드 & 배포")
_SERVICE_PLATFORM_PREFIXES = (
    (("azure ", "microsoft azure "), "Azure"),
    (("aws ", "amazon "), "AWS"),
    (("google cloud ",), "Google Cloud"),
    (("naver cloud ",), "Naver Cloud"),
)


def canonical_skill_name(name: str) -> str:
    """목록의 표준 표기를 적용하고, 목록 밖 이름은 공백만 정리한다."""

    normalized = _normalize_name(name)
    alias = _NAME_ALIASES.get(normalized)
    if alias is not None:
        return alias
    return _CANONICAL_NAME_BY_NORMALIZED.get(normalized, " ".join(name.split()))


def skill_categories_for_name(name: str) -> tuple[str, ...]:
    """기술명에 해당하는 카테고리를 반환한다. 중복 분류는 맥락에 따라 선택한다."""

    normalized = _normalize_name(name)
    canonical = _NAME_ALIASES.get(normalized)
    if canonical is not None:
        normalized = _normalize_name(canonical)
    categories = _CATEGORIES_BY_NORMALIZED_NAME.get(normalized, set())
    if not categories:
        categories = {
            "클라우드 & 배포"
            for prefixes, _representative in _SERVICE_PLATFORM_PREFIXES
            if normalized.startswith(prefixes)
            and any(
                normalized.startswith(prefix) and normalized.removeprefix(prefix).strip()
                for prefix in prefixes
            )
        }
    return tuple(category for category in SKILL_CATEGORIES if category in categories)


def platform_group_representative(names_by_member: Iterable[Iterable[str]]) -> str | None:
    """여러 확인된 클라우드 서비스가 같은 플랫폼에 속할 때만 대표명을 반환한다."""

    service_platforms = []
    for names in names_by_member:
        candidates = set()
        for name in names:
            normalized = _normalize_name(name)
            for prefixes, representative in _SERVICE_PLATFORM_PREFIXES:
                for prefix in prefixes:
                    if normalized.startswith(prefix):
                        service_name = normalized.removeprefix(prefix).strip()
                        if service_name:
                            candidates.add((representative, service_name))
        if len(candidates) != 1:
            return None
        service_platforms.append(next(iter(candidates)))

    if len(service_platforms) < 2:
        return None
    representatives = {representative for representative, _service in service_platforms}
    services = {service for _representative, service in service_platforms}
    if len(representatives) != 1 or len(services) < 2:
        return None
    return service_platforms[0][0]


def skill_display_category(name: str) -> str:
    """기본 표시 카테고리를 반환한다. 맥락이 필요한 경우 첫 번째 사전 분류를 쓴다."""

    categories = skill_categories_for_name(name)
    return categories[0] if categories else UNCATEGORIZED_SKILL_CATEGORY
