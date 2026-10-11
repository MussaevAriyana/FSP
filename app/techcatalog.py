"""Каталог технологий для опроса, профиля, потребностей и вакансий.

Формат строки: id | название | специализации (b=backend, f=frontend, d=data, o=devops, q=qa, * = все) | синонимы для разбора PDF (через «;»).
Идентификаторы стабильны: на них ссылаются профили, вакансии и подтверждение навыков по темам теста.
"""

_RAW = {
    "Языки программирования": """
python|Python|abdoqs|
java|Java|bdmq|
go|Go|bos|golang
csharp|C#|bgq|c#
cpp|C++|bdeg|c++
c|C|beo|
rust|Rust|bego|
kotlin|Kotlin|bmq|
scala|Scala|bd|
php|PHP|b|
ruby|Ruby|bq|
swift|Swift|fm|
dart|Dart|fm|
r|R|d|язык r
javascript|JavaScript|bfgq|js;ecmascript
typescript|TypeScript|bf|ts
bash|Bash|eoqs|shell
powershell|PowerShell|o|
sql|SQL|*|
""",
    "Backend: платформы и фреймворки": """
nodejs|Node.js|bf|node.js;node js
dotnet|.NET|bq|dotnet;.net
django|Django|b|
flask|Flask|b|
fastapi|FastAPI|b|
spring|Spring Framework|b|
spring_boot|Spring Boot|b|
aspnet|ASP.NET Core|b|asp.net
express|Express|b|expressjs
nestjs|NestJS|b|nest.js
laravel|Laravel|b|
symfony|Symfony|b|
rails|Ruby on Rails|b|rails
gin|Gin (Go)|b|
ktor|Ktor|b|
quarkus|Quarkus|b|
hibernate|Hibernate / JPA|b|jpa
sqlalchemy|SQLAlchemy|b|
celery|Celery|b|
""",
    "Frontend": """
html|HTML|f|html5
css|CSS|f|css3
sass|Sass / SCSS|f|scss
react|React|f|react.js;reactjs
vue|Vue.js|f|vue.js
angular|Angular|f|
svelte|Svelte|f|
nextjs|Next.js|f|next.js
nuxt|Nuxt|f|nuxt.js
redux|Redux|f|
vite|Vite|f|
webpack|Webpack|f|
tailwind|Tailwind CSS|f|
bootstrap|Bootstrap|f|
jquery|jQuery|f|
a11y|Доступность (a11y)|f|accessibility;a11y
react_native|React Native|fm|
flutter|Flutter|fm|
android|Android|fm|
ios|iOS|fm|
""",
    "Базы данных": """
postgresql|PostgreSQL|bdoq|postgres;постгрес
mysql|MySQL|bdoq|
sqlite|SQLite|bq|
mssql|Microsoft SQL Server|bd|ms sql;mssql
oracle|Oracle Database|bd|
mongodb|MongoDB|bd|mongo
redis|Redis|bo|
cassandra|Cassandra|bd|
clickhouse|ClickHouse|bd|
elasticsearch|Elasticsearch|bdo|elastic
neo4j|Neo4j|bd|
""",
    "Брокеры сообщений и API": """
kafka|Apache Kafka|bd|
rabbitmq|RabbitMQ|b|
nats|NATS|b|
rest|REST|bfq|restful
graphql|GraphQL|bf|
grpc|gRPC|b|
websockets|WebSockets|bf|websocket
openapi|OpenAPI / Swagger|bfq|openapi;swagger
""",
    "DevOps и инфраструктура": """
linux|Linux|bdeoqs|
docker|Docker|bdoqs|
kubernetes|Kubernetes|bo|k8s;кубернетес
helm|Helm|o|
terraform|Terraform|o|
ansible|Ansible|o|
podman|Podman|o|
vault|HashiCorp Vault|os|
istio|Istio|o|
nginx|Nginx|bfo|
networks|Сети (TCP/IP, DNS)|beos|tcp/ip;dns;сети;networking
ci_cd|CI/CD|bdoq|ci/cd;ci-cd
jenkins|Jenkins|oq|
gitlab_ci|GitLab CI|oq|gitlab ci
github_actions|GitHub Actions|oq|github actions
argocd|Argo CD|o|argo cd
""",
    "Мониторинг и наблюдаемость": """
prometheus|Prometheus|o|
grafana|Grafana|o|
elk|ELK / OpenSearch|o|kibana;logstash;opensearch
jaeger|Jaeger|o|
opentelemetry|OpenTelemetry|bo|
sentry|Sentry|bfo|
""",
    "Облака": """
aws|AWS|bdo|amazon web services
gcp|Google Cloud|bdo|google cloud
azure|Microsoft Azure|bdo|
yandex_cloud|Yandex Cloud|bdo|яндекс облако;yandex cloud
vk_cloud|VK Cloud|bo|
""",
    "Данные и машинное обучение": """
pandas|pandas|d|
numpy|NumPy|d|
scipy|SciPy|d|
matplotlib|Matplotlib|d|
scikit_learn|scikit-learn|d|sklearn;scikit-learn
pytorch|PyTorch|d|
tensorflow|TensorFlow|d|
keras|Keras|d|
xgboost|XGBoost|d|
catboost|CatBoost|d|
lightgbm|LightGBM|d|
huggingface|Hugging Face|d|hugging face
langchain|LangChain|d|
opencv|OpenCV|d|
ml|Машинное обучение|d|machine learning;машинное обучение
nlp|NLP|d|
cv|Компьютерное зрение|d|computer vision
statistics|Статистика|d|statistics;статистик
ab_testing|A/B-тесты|d|a/b;ab testing
spark|Apache Spark|d|pyspark
hadoop|Hadoop|d|
airflow|Apache Airflow|d|
dbt|dbt|d|
jupyter|Jupyter|d|
power_bi|Power BI|d|powerbi
""",
    "Тестирование": """
manual|Ручное тестирование|q|manual testing;ручное тестирование;тест-кейс
selenium|Selenium|q|
playwright|Playwright|q|
cypress|Cypress|q|
appium|Appium|q|
pytest|pytest|bq|
junit|JUnit|bq|
mockito|Mockito|bq|
postman|Postman|q|
api_testing|Тестирование API|q|api testing;тестирование api
jmeter|JMeter|q|
locust|Locust|q|
load_testing|Нагрузочное тестирование|oq|
cucumber|Cucumber / BDD|q|bdd;cucumber
security_testing|Тестирование безопасности|qs|
""",
    "Инженерные практики": """
git|Git|*|
github|GitHub|*|
gitlab|GitLab|*|
jira|Jira|*|
agile|Agile|*|
scrum|Scrum|*|
algorithms|Алгоритмы и структуры данных|*|алгоритм
oop|ООП|bfq|oop
design_patterns|Паттерны проектирования|bf|design patterns
solid|SOLID|bf|
clean_architecture|Чистая архитектура|b|clean architecture
microservices|Микросервисы|bo|
oauth|OAuth 2.0 / OIDC|bfs|oauth;oidc
jwt|JWT|bfs|
owasp|OWASP|bfqs|
""",
    "Мобильная разработка": """
swiftui|SwiftUI|m|
uikit|UIKit|m|
jetpack_compose|Jetpack Compose|m|compose
kmp|Kotlin Multiplatform|m|kmp
coroutines|Корутины / Flow|m|coroutines
room|Room / SQLite на устройстве|m|
firebase|Firebase|m|
mvvm|MVVM / MVI|m|mvvm
gradle|Gradle|m|
xcode|Xcode|m|
push|Push-уведомления|m|push
app_store|Публикация в App Store / Google Play|m|google play;app store
""",
    "Информационная безопасность": """
pentest|Пентест|s|penetration testing;пентест
burp|Burp Suite|s|
nmap|Nmap|s|
wireshark|Wireshark|s|
metasploit|Metasploit|s|
siem|SIEM / SOC|s|siem;soc
crypto|Криптография|s|cryptography;криптограф
tls|TLS / PKI|s|tls;pki
iam|IAM и управление доступом|s|iam
ctf|CTF|s|ctf
reverse|Реверс-инжиниринг|s|reverse engineering
forensics|Цифровая криминалистика|s|forensics
waf|WAF|s|
sast_dast|SAST / DAST|s|sast;dast
""",
    "Embedded, робототехника, системное ПО": """
stm32|STM32|e|
arduino|Arduino|e|
rtos|RTOS / FreeRTOS|e|freertos;rtos
can_bus|CAN / I2C / SPI / UART|e|can bus;i2c;spi;uart
assembler|Ассемблер|e|assembler;ассемблер
cmake|CMake|e|
gdb|GDB / отладка|e|gdb
kernel|Ядро Linux и драйверы|e|linux kernel
mqtt|MQTT|e|
ros|ROS / ROS 2|e|ros2;ros 2
verilog|Verilog / VHDL|e|vhdl;fpga
control|Теория управления|e|pid;control theory
""",
    "Разработка игр и графики": """
unity|Unity|g|
unreal|Unreal Engine|g|unreal engine
godot|Godot|g|
opengl|OpenGL / Vulkan|g|opengl;vulkan
shaders|Шейдеры|g|shader
game_math|Математика для игр|g|
ecs|ECS|g|
game_net|Сетевой код игр|g|
""",
    "Аналитика и проектирование": """
bpmn|BPMN|a|
uml|UML|a|
requirements|Сбор и анализ требований|a|requirements;требовани
user_stories|User Stories / Use Cases|a|user stories;use case
confluence|Confluence|a|
figma|Figma|a|
tableau|Tableau|a|
excel|Excel / Google Sheets|a|excel
swagger_docs|Документирование API|a|
process_mining|Process Mining|a|
""",
}

SPEC_CODE = {"b": "backend", "f": "frontend", "d": "data", "o": "devops", "q": "qa", "m": "mobile", "s": "security", "e": "embedded", "g": "gamedev", "a": "analyst"}


def _parse():
    items, seen = [], set()
    for group, block in _RAW.items():
        for line in block.strip().splitlines():
            tid, label, specs, aliases = (line.split("|") + [""])[:4]
            if tid in seen:
                raise ValueError(f"дубликат технологии: {tid}")
            seen.add(tid)
            sp = sorted(SPEC_CODE.values()) if specs == "*" else [SPEC_CODE[c] for c in specs]
            al = [a.strip().lower() for a in aliases.split(";") if a.strip()]
            items.append({"id": tid, "label": label, "group": group, "specs": sp, "aliases": al or [label.lower()]})
    return items


CATALOG = _parse()
TECH_IDS = [t["id"] for t in CATALOG]
TECH_BY_ID = {t["id"]: t for t in CATALOG}
GROUPS = list(_RAW)
