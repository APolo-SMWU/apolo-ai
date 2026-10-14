"""Skill.category 그룹의 표시 이름과 분류 참고 사전. 목록은 화이트리스트가 아니다."""

from typing import Final

from apolo.ontology.personal import SKILL_CATEGORY_IDS

SKILL_CATEGORY_CATALOG: Final[dict[str, tuple[str, str]]] = {
    "language": (
        "언어",
        "JavaScript, TypeScript, Python, Java, Kotlin, Swift, Dart, Go, Rust, C, C++, C#, PHP, "
        "Ruby, R, Scala, Julia, SQL, Bash, PowerShell",
    ),
    "web_markup_styling": (
        "웹 마크업 & 스타일링",
        "HTML, CSS, Sass, Less, Tailwind CSS, CSS Modules, Styled Components, Emotion, Bootstrap",
    ),
    "frontend": (
        "프론트엔드",
        "React, Next.js, Vue.js, Nuxt, Angular, Svelte, SvelteKit, Astro, Remix, jQuery",
    ),
    "ui_component": (
        "UI 컴포넌트",
        "MUI, Ant Design, Chakra UI, shadcn/ui, Radix UI, Headless UI, Mantine, Vuetify, "
        "Element Plus",
    ),
    "backend": (
        "백엔드",
        "Node.js, Deno, Bun, Express, NestJS, Fastify, Hono, Spring, Spring Boot, Django, Flask, "
        "FastAPI, Django REST Framework, ASP.NET Core, Laravel, Symfony, Ruby on Rails, Gin, "
        "Echo, Fiber",
    ),
    "mobile": (
        "모바일",
        "Android SDK, Jetpack Compose, Android Views, SwiftUI, UIKit, Flutter, React Native, "
        "Expo, Kotlin Multiplatform, .NET MAUI, Ionic, Capacitor",
    ),
    "desktop": ("데스크톱", "Electron, Tauri, Qt, WPF, WinUI, JavaFX, .NET MAUI"),
    "state_management": (
        "상태 관리",
        "Redux, Redux Toolkit, Zustand, Jotai, Recoil, MobX, XState, Pinia, Vuex, NgRx, Riverpod, "
        "Provider, BLoC, GetX",
    ),
    "server_state_data_fetching": (
        "서버 상태 & 데이터 패칭",
        "TanStack Query, SWR, Apollo Client, RTK Query",
    ),
    "api_communication": (
        "API & 통신",
        "REST API, GraphQL, gRPC, WebSocket, SSE, tRPC, OpenAPI, Swagger, Axios, Retrofit, "
        "OkHttp, Alamofire, Dio",
    ),
    "database": (
        "데이터베이스",
        "PostgreSQL, MySQL, MariaDB, SQLite, Oracle Database, SQL Server, MongoDB, DynamoDB, "
        "Cassandra, CouchDB, Neo4j, Cloud Firestore, Firebase Realtime Database",
    ),
    "orm_data_access": (
        "ORM & 데이터 접근",
        "Prisma, TypeORM, Sequelize, Drizzle ORM, Hibernate, JPA, Spring Data JPA, MyBatis, "
        "SQLAlchemy, Django ORM, Entity Framework Core, Mongoose, Room, Core Data",
    ),
    "cache_search": (
        "캐시 & 검색",
        "Redis, Memcached, Elasticsearch, OpenSearch, Apache Solr, Meilisearch, Algolia",
    ),
    "messaging_event_streaming": (
        "메시징 & 이벤트 스트리밍",
        "Apache Kafka, RabbitMQ, Apache Pulsar, NATS, Amazon SQS, Amazon SNS, "
        "Google Cloud Pub/Sub, Amazon Kinesis",
    ),
    "auth_security": (
        "인증 & 보안",
        "OAuth 2.0, OpenID Connect, JWT, SAML, WebAuthn, Spring Security, Passport.js, Auth.js, "
        "Keycloak, Auth0, Firebase Authentication, OWASP, Vault, Wireshark, Burp Suite, Nmap, "
        "Metasploit, Snort",
    ),
    "architecture_design": (
        "아키텍처 & 설계",
        "UML, PlantUML, Mermaid, draw.io, StarUML, Enterprise Architect, Structurizr, ERDCloud, "
        "dbdiagram.io",
    ),
    "build_package_tool": (
        "빌드 & 패키지 도구",
        "Vite, Webpack, Rollup, Parcel, esbuild, SWC, Babel, Turbopack, npm, Yarn, pnpm, Maven, "
        "Gradle, Poetry, uv, pip, Bundler, NuGet, Turborepo, Nx",
    ),
    "dev_automation_tool": (
        "개발 & 자동화 도구",
        "Git, GitHub CLI, Make, Task, pre-commit, Husky, lint-staged, Plop, Hygen, n8n, Zapier, "
        "Make.com",
    ),
    "ci_cd": (
        "CI/CD",
        "GitHub Actions, GitLab CI/CD, Jenkins, CircleCI, Travis CI, Azure Pipelines, Argo CD, "
        "Tekton, AWS CodePipeline, Bitrise, Codemagic, Fastlane",
    ),
    "container_infra_automation": (
        "컨테이너 & 인프라 자동화",
        "Docker, Docker Compose, Podman, Kubernetes, Helm, Kustomize, Terraform, OpenTofu, "
        "Pulumi, AWS CloudFormation, AWS CDK, Ansible, Packer",
    ),
    "cloud_deployment": (
        "클라우드 & 배포",
        "AWS, Google Cloud, Microsoft Azure, Naver Cloud, Vercel, Netlify, Cloudflare Workers, "
        "Cloudflare Pages, Render, Railway, Fly.io, Heroku, Firebase Hosting, Amazon EC2, "
        "Amazon ECS, Amazon EKS, AWS Lambda, Google Cloud Run",
    ),
    "storage_cdn": (
        "스토리지 & CDN",
        "Amazon S3, Google Cloud Storage, Azure Blob Storage, Cloudflare R2, Amazon CloudFront, "
        "Cloudflare CDN, Cloudinary",
    ),
    "os_server": (
        "운영체제 & 서버",
        "Linux, Ubuntu, Debian, RHEL, Alpine Linux, Windows Server, Nginx, Apache HTTP Server, "
        "Caddy, IIS, Apache Tomcat",
    ),
    "network": ("네트워크", "HTTP, HTTPS, TCP/IP, DNS, TLS, VPN, VPC"),
    "testing_quality": (
        "테스트 & 품질",
        "Jest, Vitest, Testing Library, Mocha, Chai, Jasmine, JUnit, Mockito, Pytest, unittest, "
        "PHPUnit, RSpec, xUnit, NUnit, Playwright, Cypress, Selenium, Puppeteer, Appium, "
        "Espresso, XCTest, Detox, Maestro, Postman, Newman, REST Assured, Supertest, k6, JMeter, "
        "Locust, ESLint, Prettier, Biome, Ruff, mypy, SonarQube",
    ),
    "monitoring_observability": (
        "모니터링 & 관측",
        "Prometheus, Grafana, Datadog, New Relic, Sentry, OpenTelemetry, Jaeger, Zipkin, "
        "Amazon CloudWatch, Elastic Stack, Loki, Fluentd, Fluent Bit",
    ),
    "data_collection_processing": (
        "데이터 수집 & 처리",
        "pandas, NumPy, Polars, SciPy, tidyverse, Apache Spark, Apache Hadoop, Apache Flink, "
        "Apache Beam, Dask, Scrapy, Beautiful Soup, Selenium",
    ),
    "data_pipeline": (
        "데이터 파이프라인",
        "Apache Airflow, Dagster, Prefect, dbt, Airbyte, Fivetran, Apache NiFi, Luigi, AWS Glue",
    ),
    "data_warehouse_lakehouse": (
        "데이터 웨어하우스 & 레이크하우스",
        "BigQuery, Snowflake, Amazon Redshift, Azure Synapse Analytics, Databricks, DuckDB, "
        "ClickHouse, Trino, Apache Hive, Delta Lake, Apache Iceberg, Apache Hudi",
    ),
    "data_analysis_bi": (
        "데이터 분석 & BI",
        "Excel, Google Sheets, Power Query, Power Pivot, Tableau, Power BI, Looker, "
        "Looker Studio, Metabase, Apache Superset, GA4, Amplitude, Mixpanel",
    ),
    "data_visualization": (
        "데이터 시각화",
        "Matplotlib, Seaborn, Plotly, Bokeh, Altair, ggplot2, D3.js, Chart.js, Recharts, "
        "Apache ECharts, Highcharts",
    ),
    "statistics_experiment": (
        "통계 & 실험",
        "SPSS, SAS, Stata, JASP, jamovi, Minitab, statsmodels, PyMC, Optimizely, GrowthBook",
    ),
    "machine_learning": (
        "머신러닝 & 딥러닝",
        "scikit-learn, XGBoost, LightGBM, CatBoost, PyTorch, TensorFlow, Keras, JAX, "
        "Hugging Face Transformers, PyTorch Lightning, CUDA",
    ),
    "nlp_computer_vision": (
        "자연어 처리 & 컴퓨터 비전",
        "spaCy, NLTK, Gensim, Sentence Transformers, KoNLPy, OpenCV, torchvision, Detectron2, "
        "Ultralytics YOLO, Tesseract",
    ),
    "generative_ai_llm": (
        "생성형 AI & LLM",
        "OpenAI API, Anthropic API, Gemini API, LangChain, LangGraph, LlamaIndex, "
        "Semantic Kernel, DSPy, PEFT",
    ),
    "vector_search": (
        "벡터 검색 & 데이터베이스",
        "FAISS, pgvector, Pinecone, Weaviate, Milvus, Chroma, Qdrant, Annoy",
    ),
    "knowledge_graph_ontology": (
        "지식 그래프 & 온톨로지",
        "RDF, RDFS, OWL, SPARQL, SHACL, JSON-LD, Protégé, Apache Jena, RDFLib, GraphDB, Stardog",
    ),
    "mlops_model_serving": (
        "MLOps & 모델 서빙",
        "MLflow, Weights & Biases, DVC, Kubeflow, TensorBoard, Optuna, Ray Tune, BentoML, KServe, "
        "Seldon Core, NVIDIA Triton, TorchServe, TensorFlow Serving, ONNX Runtime, vLLM, "
        "Amazon SageMaker, Vertex AI, Evidently",
    ),
    "design_prototyping": (
        "디자인 & 프로토타이핑",
        "Figma, Sketch, Adobe XD, Framer, ProtoPie, Photoshop, Illustrator, After Effects, Lottie",
    ),
    "docs_collaboration": (
        "문서화 & 협업",
        "GitHub, GitLab, Bitbucket, Notion, Confluence, Jira, Linear, Trello, Slack, "
        "Microsoft Teams, Miro, FigJam, Storybook, Docusaurus, MkDocs",
    ),
    "game_realtime_graphics": (
        "게임 & 실시간 그래픽",
        "Unity, Unreal Engine, Godot, Cocos Creator, Three.js, Babylon.js, WebGL, WebGPU, OpenGL, "
        "Vulkan, DirectX",
    ),
    "embedded_iot": (
        "임베디드 & IoT",
        "Arduino, ESP-IDF, STM32 HAL, FreeRTOS, Zephyr, Embedded Linux, ROS, ROS 2, MQTT, "
        "PlatformIO",
    ),
    "other": ("기타", ""),
}

assert tuple(SKILL_CATEGORY_CATALOG) == SKILL_CATEGORY_IDS
