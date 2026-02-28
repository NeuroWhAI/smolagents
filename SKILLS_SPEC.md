# smolagents에 Skills 기능 추가를 위한 심층 리서치 기반 구현 계획서

smolagents는 “에이전트가 코드로 생각한다”는 철학 아래, 핵심 로직을 작게 유지하면서도(CodeAgent/ToolCallingAgent, 샌드박스 실행, Hub 기반 공유) 실전 배포에 필요한 구성요소를 일관된 방식으로 제공한다. citeturn0view0  
본 계획서는 smolagents의 기존 추상화(`MultiStepAgent`, `Tool`, prompt template, sandbox executors, Hub 신뢰 모델)를 최대한 재사용하여, Agent Skills(AgentSkills 표준(https://agentskills.io/specification 참고)의 `SKILL.md` + progressive disclosure)를 “smolagents스럽게” 도입하는 구현 로드맵과 PR 구조를 제시한다. citeturn2view5turn3view0turn6view4  
핵심 설계는 (1) **startup 시 skill 메타데이터 인덱스만 주입**, (2) **트리거 시 선택된 스킬 본문/리소스만 지연 로딩**, (3) **파일시스템 접근 가능 환경에서는 CodeAgent의 파이썬 실행을 기본 경로로 활용**, (4) 비-파일시스템 환경에서는 **skill 전용 Tool(activate/read) 자동 주입**으로 보완하는 “이중 경로”다. citeturn0view0turn3view0turn6view4  

## Repository 분석

### 저장소 개요와 설계 철학

- 저장소 루트 구조는 `.github/`, `docs/`, `examples/`, `src/smolagents/`, `tests/` 및 `AGENTS.md` 등을 포함한다. citeturn0view0  
- README에서 smolagents는 “agents that think in code”를 내세우며, 핵심 코드가 `agents.py`에 ~1,000 LOC 수준으로 유지된다고 명시한다(= 기능 추가 시 과도한 프레임워크화보다 최소 추상화 선호). citeturn0view0  
- CodeAgent의 보안 실행은 E2B/Modal/Docker/WASM 등 다양한 샌드박스 백엔드를 지원하도록 설계되어 있으며, 이는 Skills(서드파티 지식/스크립트) 도입 시에도 동일한 보안 경로를 재사용할 수 있음을 시사한다. citeturn0view0turn2view4  

### 빌드/테스트/스타일/의존성 정책

- Python 요구사항은 `>=3.10`이며, 패키지 메타데이터(`name`, `version`, `dependencies`, extras, ruff/pytest 설정)가 `pyproject.toml`에 통합되어 있다. (pyproject.toml L0-L2) citeturn2view0  
- 기본 의존성에 `huggingface-hub`(버전 상한 `<1.0.0`), `requests`, `rich`, `jinja2`, `pillow`(보안 CVE 대응 주석 포함), `python-dotenv` 등이 포함되어 있으며, extras로 `mcp`, `telemetry`, `docker`, `e2b`, `modal`, `openai` 등을 분리 제공한다. (pyproject.toml L0-L2) citeturn2view0  
- 코드 품질 도구는 `ruff`(line-length=119, 특정 lint ignore 포함)이며, pre-commit도 ruff로 구성되어 있다. (`pyproject.toml` L2, `.pre-commit-config.yaml` L0) citeturn2view0turn2view2  
- 개발 워크플로는 `Makefile`의 `make quality/style/test`로 정리되어 있고, 테스트는 `pytest ./tests/`로 실행된다. (Makefile L0, CONTRIBUTING.md L8-L9) citeturn2view3turn2view1  
- CONTRIBUTING은 dev 설치(`pip install -e ".[dev]"` 또는 uv)와 품질/테스트 실행 방법을 명확히 안내한다. (CONTRIBUTING.md L8-L9) citeturn2view1  

### 릴리스/버전/유지보수 주체

- 저장소는 GitHub Releases를 운영하며, 최신 릴리스로 `v1.24.0`(2026-01-16)을 표시한다. (repo root L539-L543) citeturn0view0  
- 현재 개발 버전은 `1.25.0.dev0`로 보이며, “messages → steps” deprecation이 1.25에서 제거 예정임을 `agents.py`에서 경고한다(호환성 고려 필요). (pyproject.toml L0-L1, agents.py L8-L10) citeturn2view0turn2view5  
- 프로젝트는 Hugging Face가 리드/관리하며, CONTRIBUTING에서도 “Hugging Face 주도”와 외부 유지관리자 참여 가능성을 언급한다. (CONTRIBUTING.md L9) citeturn2view1  
- pyproject의 authors에 Aymeric Roucher가 포함되어 있어, 최소 리뷰 요청자 후보로 삼을 수 있다. (pyproject.toml L0-L1) citeturn2view0  

### 기존 Agent/Tool 추상화와 Skills가 들어갈 “자리”

**Agent 핵심 (agents.py)**  
- `MultiStepAgent`는 `prompt_templates["system_prompt"]` 기반으로 시스템 프롬프트를 생성하며, `instructions` 파라미터로 사용자 커스텀 지시를 system prompt에 삽입할 수 있다. (agents.py L11-L16) citeturn2view5  
- `self.tools`는 `{tool.name: tool}` dict로 관리되며, base tools를 옵션으로 추가하고 마지막에 `final_answer` tool을 보장한다. (agents.py L15-L17) citeturn2view5  
- `run()`에서 `additional_args`를 `self.state`에 주입하고 task 문자열에 “추가 인자 제공” 문장을 덧붙이는 방식으로 컨텍스트 전달을 한다. (agents.py L20-L21) citeturn2view5  

**Tool 핵심 (tools.py)**  
- `Tool`은 `name/description/inputs/output_type`을 필수로 요구하며, `forward()` 시그니처가 inputs 키와 일치해야 한다(엄격한 인터페이스). (tools.py L3-L8) citeturn3view0  
- `setup()`는 “비싼 초기화는 최초 호출 시 1회” 수행하도록 설계되어 있다(= Skills 로더/인덱서에도 유사한 lazy-init 가능). (tools.py L6-L9) citeturn3view0  
- `to_code_prompt()`는 CodeAgent가 tool 함수를 “파이썬 함수 시그니처 + docstring(입출력/스키마)”로 이해하도록 prompt에 인코딩하는 기능을 제공한다. 특히 `output_schema`가 있으면 “structured output 도구”임을 강조하는 문구를 자동 삽입한다. (tools.py L10-L12) citeturn3view0  
- Hub에서 툴을 로드할 때 `trust_remote_code=True`를 요구하며, “pip/npm 설치처럼 검사하라”는 경고를 포함한다(= Skills도 같은 신뢰 모델을 가져가야 smolagents 철학과 합치). (tools.py L21-L24, L32-L34) citeturn3view0  

**보안 안내(SECURITY.md)**  
- 보안 취약점 신고 채널과 함께, secure code execution 튜토리얼 및 E2B/Modal/Docker/WASM 샌드박스 옵션을 안내한다. (SECURITY.md L0-L1) citeturn2view4  

---

### 수정/추가가 필요한 파일·경로 목록(초안)

| 변경 대상 | 위치(경로) | 변경 이유(요약) |
|---|---|---|
| Skills 데이터 모델/로딩 | `src/smolagents/skills.py` (신규) 또는 `src/smolagents/skills/` (신규 패키지) | agents.py를 비대화시키지 않고(“smol” 철학), 메타데이터 파싱/인덱싱/로딩을 분리 |
| Skills 프롬프트 주입 훅 | `src/smolagents/agents.py` | `initialize_system_prompt()` 또는 system prompt 템플릿 렌더링 경로에서 skills-index를 삽입 (system_prompt read-only 구조 고려) citeturn2view5 |
| Skills 전용 Tool (옵션) | `src/smolagents/skill_tools.py` (신규) 혹은 `src/smolagents/default_tools.py`에 등록 | 비-파일시스템 환경에서 `activate_skill/read_skill_resource` 제공(사용자 의견 반영) |
| CLI 확장 | `src/smolagents/cli.py` | `smolagent`/`webagent`와 동일한 CLI 체계로 `smolagent skills ...` subcommand 추가(등록/스캔/검증) citeturn2view0 |
| 문서 | `README.md`, `docs/source/...` | Skills 개념/경로/템플릿/보안 경고/스킬 작성 체크리스트 추가 citeturn2view4turn2view1 |
| 테스트 | `tests/test_skills_*.py` (신규) | 파서/인덱서/라우터/도구 경로별(E2E) 회귀 테스트 |
| 보안/기여 가이드 | `SECURITY.md`, `CONTRIBUTING.md` | 서드파티 스킬 위험(프롬프트 인젝션/스크립트), 리뷰·권한 모델·신뢰 플래그 추가 citeturn2view4turn2view1 |

## Proposed Skills 설계

### 목표: smolagents의 “작고 직접적인 코드 기반” 철학과의 정합성

smolagents는 이미 (a) CodeAgent가 파이썬 코드를 실행할 수 있고, (b) tool을 파이썬 함수처럼 이해시키는 프롬프트 인코딩을 제공하며, (c) 샌드박스 실행 옵션을 제공한다. citeturn0view0turn3view0turn2view4  
따라서 Skills는 새로운 거대한 서브시스템이 아니라, 다음의 최소 기능을 추가하는 형태가 가장 “fit”하다.

- **Skill Index(메타데이터 목록)**: startup에 system prompt에 “스킬 목록”만 전달  
- **Skill Body Loader(지연 로딩)**: 선택된 스킬만 본문을 읽어 추가 지시로 삽입  
- **Resource Access**: 파일시스템 접근 가능한 경우 CodeAgent의 파이썬 실행으로 해결, 그렇지 않으면 전용 Tool 제공(사용자 의견 반영) citeturn0view0turn3view0  

### 데이터 모델: `SKILL.md` frontmatter 스키마

기본은 AgentSkills 표준을 따르되, smolagents 특화 필드를 최소 추가한다. (표준: `name`, `description`, optional `metadata`, `compatibility`, 디렉터리 레이아웃, progressive disclosure 등) citeturn6view4  

**필수 필드**  
- `name: str` — Python 식별자 호환 권장(툴/에이전트 이름 검증과 일관) citeturn2view5turn3view0  
- `description: str` — 트리거의 1차 신호(짧고 구체적으로)

**권장 필드(표준 호환)**  
- `compatibility` — OS/런타임 요구, sandboxes 요구 등  
- `metadata` — provenance/version/permissions(아래) 등 JSON-serializable dict

**smolagents 확장(제안)**  
- `smolagents:` 하위에 아래 키만 허용(과도한 DSL 방지)
  - `permissions`: `{ fs_read: bool, fs_write: bool, network: "deny|allow", sandbox: "required|preferred|none", tools: [str] }`
  - `entrypoints`: `{ default: { kind: "instructions" }, tool_dispatch?: { tool: str, arg_mode: "json|raw" } }` (OpenClaw의 “command-dispatch tool” 아이디어를 smolagents Tool에 맞게 축약) citeturn15view0turn3view0  

### 저장소(스토리지)와 배포 스코프

smolagents는 이미 Hub를 통한 Tool 공유(`push_to_hub`, `from_hub`)에 “trust_remote_code” 모델을 갖고 있다. (tools.py L18-L24) citeturn3view0  
Skills도 동일한 신뢰 모델을 가져가면 철학적으로 일관된다.

**로컬 FS 스토리지(기본)**  
- repo-local: `<repo_root>/.smolagents/skills/<skill_name>/SKILL.md`  
- user-global: `~/.smolagents/skills/<skill_name>/SKILL.md`  
- env override: `SMOLAGENTS_SKILLS_DIRS="...:..."`
  
이 패턴은 Codex/Claude/OpenClaw가 “프로젝트/사용자 전역” 스코프를 분리하는 것과 유사하지만, 경로는 smolagents 네이밍에 맞춤. citeturn0view0turn6view4  

**레지스트리(선택, v2+)**  
- Hugging Face Hub를 Skills 배포 채널로 사용: `smolagents-skills/<skill_repo>` 같은 Space/Repo  
- `Skill.from_hub(..., trust_remote_code=True)`로 로딩(도구와 동일한 위험 고지/플래그) citeturn3view0  

### 메타데이터 인덱스와 progressive disclosure 로딩 전략

AgentSkills 표준의 핵심은 3단계 progressive disclosure다: (1) 메타데이터는 시작 시(저토큰), (2) 본문은 트리거 시, (3) 리소스/스크립트는 필요 시 로드. citeturn6view4turn13view0  
smolagents에선 이를 다음처럼 구현한다.

- **Index 구축 시점**: `MultiStepAgent.__init__` 혹은 `system_prompt` 생성 직전  
- **Index 내용**: `(name, description, location, version?, compatibility?)`만 포함  
- **Body 로딩**: 라우터가 skills를 선택한 직후, `SKILL.md` 본문(= frontmatter 제외)을 “추가 지시(instructions)”로 삽입  
- **Resource 로딩**:  
  - FS 가능: CodeAgent가 파이썬으로 `Path.read_text()` 직접 수행(추가 tool 없이) — 사용자 의견의 “툴은 필수 아님”을 그대로 반영 citeturn0view0turn2view5  
  - FS 불가: `activate_skill`/`read_skill_resource` Tool 제공(아래)  

### 인터페이스(호출 시그니처/스키마/에러 semantics)

smolagents의 Tool은 `inputs`·`output_type`·`output_schema`를 가진다. (tools.py L3-L6) citeturn3view0  
Skills도 “도구처럼 엄격한 타입”이 아니라 “지시문 패키지”지만, 비-FS 환경에서 제공될 Skill Tools는 Tool 규약을 따른다.

**Tool: `activate_skill` (옵션, v1)**  
- inputs: `{ name: string }`  
- output_type: `string` 또는 `object`  
- output_schema(권장):  
  ```json
  {
    "type": "object",
    "properties": {
      "name": {"type":"string"},
      "body": {"type":"string"},
      "tree": {
        "type":"array",
        "items": {"type":"string"},
        "description":"relative file paths under skill dir"
      }
    },
    "required": ["name","body"]
  }
  ```
- 에러 semantics:  
  - NotFound: 모델이 복구할 수 있도록 “모델 가시적” 오류 문자열(예: `SkillNotFound: ...`) 반환  
  - PermissionDenied: 권한 모델(아래)에서 차단되면 명시적 메시지 반환  
  - ParseError: frontmatter 파싱 실패 시 검증 오류 반환

**Tool: `read_skill_resource` (옵션, v1)**  
- inputs: `{ name: string, path: string }`  
- output_type: `string` (혹은 바이너리/이미지면 `any`로 시작하고 v2에서 확장)

이 Tool 설계는 smolagents가 “tool을 code prompt로 인코딩”하는 `to_code_prompt()`를 그대로 활용할 수 있다. (`output_schema`가 있으면 structured output 사용법까지 프롬프트에 자동 삽입) citeturn3view0  

### 권한 모델

smolagents는 도구 로딩 시 “remote code trust”를 플래그로 강제한다. (tools.py L21-L24) citeturn3view0  
Skills도 동일한 기본 철학을 취한다.

- **로컬 스킬**: 기본 신뢰(단, “서드파티 다운로드 스킬”은 trust 필요)  
- **Hub 스킬**: `trust_remote_code=True` 또는 `trust_remote_skill=True`를 요구(이름은 논의 가능)  
- **권한 최소화**:  
  - `smolagents.permissions`가 `sandbox: required`면 CodeExecutor가 Docker/E2B/Modal/WASM 중 가능한 것을 선택하도록 가이드(이미 보안 실행 옵션이 문서화됨) citeturn2view4turn0view0  
  - network/FS write 요구가 있으면, 에이전트 실행 옵션(예: DockerExecutor)과 연동해 “허용된 경우에만” 실행

### 버전/의존성 핸들링

- 버전은 `metadata.version`(SemVer 권장)을 표준 메타데이터로 저장  
- 의존성은 2계층으로 나눔:
  1) **런타임 의존성**: (python packages, system binaries) — v1에서는 “문서/가이드로 명시”하고 자동 설치는 하지 않음(보안/철학상)  
  2) **도구 의존성**: “이 스킬은 특정 Tool이 있어야 한다” — v1에서 `smolagents.permissions.tools`로 선언하고, 없으면 게이팅  
- smolagents 자체 dependency policy는 버전 상한을 둔 패키지(huggingface-hub `<1.0.0`) 등 보수적 성격이므로, “스킬이 자체적으로 pip install을 유도”하는 패턴은 보안상 제한해야 한다. (pyproject.toml L0-L1, SECURITY.md L0-L1) citeturn2view0turn2view4  

## Prompt injection & context strategy

### 스킬 메타데이터 주입 포맷

smolagents는 “Markdown 지향” UI를 rich/Markdown으로 렌더링하지만, LLM 컨텍스트 효율을 생각하면 “압축된 정형 포맷”이 유리하다. citeturn2view5turn0view0  

권장: **Compact Markdown 리스트(기본) + JSON(옵션)** 하이브리드

- **Compact Markdown list (default)**  
  ```
  Available skills:
  - <name>: <one-line description> (location: repo|user|hub)
  ...
  ```
  장점: smolagents 문서/예시 스타일과 일치, 디버깅 용이  
  단점: 파싱/라우팅을 “모델”에 더 의존  

- **Compact JSON (optional)**  
  ```
  <skills_json>{"skills":[{"name":"...","description":"...","loc":"repo"}]}</skills_json>
  ```
  장점: 라우터/툴이 추출하기 쉬움  
  단점: Markdown 친화성 낮음

OpenClaw가 XML을 사용하는 사례는 참고 가능하지만, smolagents는 “코드/문서 기반 가독성”이 중요하므로 기본은 Markdown이 합리적이라는 사용자 의견을 채택한다. citeturn16view1  

### 토큰 예산/캐싱 전략

- **Index는 저토큰으로 제한**: `name`과 “한 줄 description”만 포함(MVP에서는 homepage/examples 제외)  
- **스킬 개수 상한**: system prompt에 주입되는 스킬 수를 기본 30~50개로 제한하고, 초과하면 “검색 라우터 도구”나 “prefix match”로 2차 선택하는 전략(v2)  
- **캐시**:  
  - 메타데이터 인덱스는 에이전트 인스턴스 생명주기 동안 캐시(파일 mtime 변화 감지 시 갱신)  
  - 본문/리소스는 LRU 캐시(옵션)  
- smolagents는 이미 `Tool.setup()`를 최초 호출 시 1회만 수행하도록 설계했으므로, SkillIndex도 `setup` 유사 패턴으로 lazy-init을 구현하면 코드 스타일이 유사해진다. (tools.py L6-L9) citeturn3view0  

### 스킬 개념을 모델에게 “짧게” 가르치는 프롬프트

system prompt에 아래 3~6줄 정도를 추가(템플릿 변수화) 권장:

- “skill은 절차적 지시/리소스 묶음이며, 사용할 때는 (a) 목록에서 고르고 (b) 필요할 때만 본문을 로드하며 (c) 불필요한 로드는 피한다.”  
- “스킬을 활성화하면 해당 지시를 우선 적용하되, 안전/권한 정책을 위반하지 않는다.”  
- 비-FS 환경에서는 `activate_skill`/`read_skill_resource`를 사용 가능(있을 때만 안내)

이 방식은 `agents.py`가 이미 `instructions`를 system prompt에 삽입하는 구조와 잘 맞는다. (agents.py L11-L16) citeturn2view5  

## Runtime architecture

### 아키텍처(mermaid)

```mermaid
flowchart TB
  U[User task] --> A[MultiStepAgent.run()]
  A --> SP[System prompt builder<br/>(templates + instructions)]
  SP --> SI[SkillIndex injection<br/>(metadata only)]
  SI --> M[Model generate step]
  M -->|select skill?| R[Router/Selector]
  R -->|yes| L[SkillLoader<br/>(load SKILL.md body)]
  L --> M2[Model continues with skill body]
  M2 --> EX[Code execution / tools]
  EX -->|FS available| PY[PythonExecutor reads skill resources]
  EX -->|FS unavailable| ST[Skill Tools<br/>(activate_skill/read_skill_resource)]
  EX --> OBS[Logging/metrics]
  EX --> SBX[Sandbox executor<br/>(E2B/Modal/Docker/WASM)]
```

이 구조는 smolagents의 ReAct 루프(Generate→Execute→Observe)에서 “system prompt 구성 단계”에 SkillIndex를 끼워 넣는 최소침습 방식이다. citeturn0view0turn2view5  

### 구성요소 설계

**Skill Registry/Loader** (`src/smolagents/skills.py`)  
- 책임:
  - 디렉터리 스캔, `SKILL.md` frontmatter 파싱  
  - `SkillMeta` 리스트 생성 + 캐싱  
  - 본문 로딩( frontmatter 제거 )  
  - 리소스 트리 리스트업(`tree`)

**Router/Selector** (`src/smolagents/skills_router.py` or `skills.py` 내부)  
- v1(MVP): lexical scoring(단어 겹침) + optional “LLM confirm”(추후)  
- v2: `rank-bm25`를 선택적으로 사용(이미 test extras에 포함) (pyproject.toml L1-L2) citeturn2view0  
- v3: embedding/LLM router (선택)  

**Sandbox/Permission enforcement**  
- 최소 요구: skill metadata의 `sandbox: required`면 로컬 실행이 아니라 Docker/E2B/Modal/WASM executor로 실행하도록 docs/CLI에서 강제 또는 경고(기본은 경고 → v2에서 강제). citeturn2view4turn0view0  

**Tool executor / concurrency / timeouts / retries**  
- smolagents는 `ThreadPoolExecutor`를 이미 사용하며, 모델 생성·도구 호출을 스트리밍/동기 방식으로 제공한다. (agents.py L2, L21-L22) citeturn2view5  
- Skills 도입 시 목표는 “스킬 로딩/리소스 읽기”가 병목이 되지 않게:
  - file IO는 sync로도 충분(대부분 짧음)  
  - remote Hub 로딩은 timeout + retry 필요(단, v1에서는 Hub 로딩 자체를 optional로)  
- 테스트 extras에 `pytest-timeout`이 포함되어 있어, E2E에서 스킬 로딩/실행 시간 상한 검증 가능. (pyproject.toml L1-L2) citeturn2view0  

**Observability(Tracing/Metrics)**  
- smolagents는 `Monitor`, `TokenUsage`, `AgentLogger`를 이미 갖고 있으므로, `skills_selected`, `skills_loaded_bytes`, `skill_trigger_reason` 같은 카운터를 `monitor.update_metrics`에 추가하는 방식이 자연스럽다. (agents.py L2, L20-L23) citeturn2view5  

**Security(Secrets redaction, provenance)**  
- smolagents는 이미 remote tool 로딩에서 “inspect before trust”를 강제하므로, skill도 동일하게:
  - Hub skill: `trust_remote_skill=True` 없으면 로딩 실패  
  - provenance tag(meta에 `source: local|hub`, `repo_id`, `revision`)를 trace/log에 기록  
- secrets redaction은 최소 “SKILL.md/리소스에 환경변수 값이 섞이지 않도록” 문서 가이드로 시작하고(v1), telemetry extras(OpenTelemetry 등)까지 고려하는 마스킹은 v2에서 제공. (pyproject.toml telemetry extra L0-L2) citeturn2view0  

## Execution patterns

### sync vs async

smolagents의 핵심 루프는 `run(stream=False)`면 내부적으로 generator를 모두 소비하고 마지막 `FinalAnswerStep`을 반환하는 구조다. (agents.py L18-L22) citeturn2view5  
Skills MVP는 이 흐름을 유지하고, 스킬 로딩은 “단일 단계”로 삽입한다. (비동기화는 v2에서 Hub 로딩/네트워크 리소스에만 제한적으로 도입)

### pipeline/parallel/fallback

- **Pipeline(권장 기본)**:  
  1) skill index 주입  
  2) agent가 스킬 결정  
  3) 선택된 스킬 본문 주입  
  4) CodeAgent 실행(코드/툴 호출)  
- **Parallel**:  
  - 동일 스텝에서 여러 리소스를 읽는다면 CodeAgent 상에서 병렬화는 가능하지만, side-effect(파일 write 등)와 섞일 수 있어 기본은 순차 권장  
- **Fallback**:  
  - 스킬 로딩 실패 시 “스킬 없이 일반 동작으로 복귀”  
  - 스킬이 요구하는 권한이 현재 실행 모드와 충돌 시(예: sandbox required인데 local executor만 가능) → 에러로 중단하지 말고 “권한/실행 옵션 변경 안내”를 출력

### idempotency / transaction 패턴

smolagents는 코드 실행이 side-effect를 만들 수 있으므로, Skills도 “작업을 파괴적으로 만들지 않도록” 강한 가이드를 제공해야 한다.

- 파일 변경 스킬: patch 기반/backup 생성 등 지시(문서/템플릿)  
- 외부 API 호출 스킬: 가능한 경우 idempotency key 사용 지시(문서)  
- “자동 재시도”는 tool 레벨에서만, 그리고 idempotent한 호출에만 적용(초기에는 기본 0회 권장)

### 레이트리밋 대응

smolagents는 다양한 모델/프로바이더를 지원하므로(API providers), 스킬 본문에 “429/backoff” 같은 운영 가이드를   포함시키는 것이 실용적이다. README에서도 프로바이더 교체를 쉽게 예시한다. citeturn0view0  

## Evaluation & rollout

### 측정 지표

smolagents는 TokenUsage/timing을 수집하는 monitor를 가지고 있으므로, Skills 도입 시 다음 지표를 구조적으로 남긴다. (agents.py L20-L23) citeturn2view5  

- Trigger precision/recall(오프라인 평가):  
  - 스킬이 “써야 할 과제”에서 호출되었는가  
  - 스킬이 “쓰면 안 될 과제”에서 호출되지 않았는가  
- Latency:  
  - Index build 시간  
  - Skill body load 시간  
  - 총 run 시간  
- Cost proxy:  
  - TokenUsage 변화(스킬 주입 전/후)  

### A/B 테스트 계획(선택)

- v1에서는 기능 플래그로 “skills enabled” on/off 비교  
- v2에서 “라우터 변경(bm25 vs 단순 lexical)”을 A/B로 비교  
- 결과는 `RunResult.steps` 기반(“messages deprecated → steps”로 가는 전환을 반영). (agents.py L8-L10) citeturn2view5  

### 자동화 테스트(E2E)와 CI 통합

- unit: frontmatter 파싱, 본문 추출, 트리 리스트업, 인덱스 포맷  
- integration:  
  - CodeAgent가 FS skill을 읽어 지시를 따르는지(샘플 스킬로)  
  - FS 불가 시 Skill Tools 경유로 동일 동작을 하는지  
- timeouts: `pytest-timeout`을 이용해 “skill 로딩이 무한 대기하지 않음” 검증 (pyproject.toml L1-L2) citeturn2view0  

### fuzzing/static analysis(프롬프트 인젝션)

v1에서 “완전 자동 분석”은 과하지만, 최소한 아래를 CI에 넣는다.

- `SKILL.md` 템플릿/예제에 **금지 패턴**을 문서화(예: “비밀키 출력”, “무제한 네트워크 호출”, “시스템 프롬프트 변경 지시”)  
- (선택) 간단한 정규식 린트: 위험 키워드/URL/credential pattern 탐지  
- SECURITY.md가 “untrusted code는 sandbox 권장”을 이미 강조하므로, Skills 문서도 동일한 톤으로 “검토/샌드박스”를 강조한다. citeturn2view4  

## Developer experience

### README/CONTRIBUTING 업데이트

- README: “Skills” 섹션 추가  
  - 기본 경로(예: `.smolagents/skills`)  
  - progressive disclosure: 메타만 주입/본문은 활성화 시 로드  
  - FS 가능 환경 vs 불가 환경에서의 차이  
- CONTRIBUTING: “Skills PR 체크리스트” 섹션 추가  
  - 보안/권한/샌드박스 요구사항 명시  
  - 재현 가능한 E2E 테스트 포함 요구  
  - `make quality/test` 통과를 명시(기존 문서 흐름과 일치). citeturn2view1turn2view3  

### 예제 `SKILL.md` 템플릿

`docs/skills/template/SKILL.md` (또는 `examples/skills/...`) 제공:

- name/description  
- When to use / When NOT to use  
- Preconditions (권한/환경)  
- Steps  
- Failure recovery  
- Security notes (secrets/PII)  
- Definition of done  

### CLI tooling

smolagents는 `project.scripts`로 `smolagent`, `webagent` CLI를 노출한다. (pyproject.toml L2) citeturn2view0  
따라서 `smolagent skills` 서브커맨드가 자연스럽다.

- `smolagent skills scan` — skill dirs 스캔, 인덱스 출력  
- `smolagent skills validate` — frontmatter/디렉터리 구조 검증  
- v2: `smolagent skills publish --hub <repo_id>` — Hub push(단, trust 모델/리뷰 모델 합의 후)

## Implementation roadmap & PR plan

### 마일스톤/일정/노력 추정

기본 가정: 1명 기준 person-week(순수 구현+리뷰 대응 포함). smolagents는 도구/에이전트/샌드박스/Hub 관련 기존 코드가 있어 재사용 가능하므로 “MVP는 비교적 빠르게” 가능하되, 보안/문서/테스트가 품질을 좌우한다. citeturn3view0turn2view5turn2view4  

| 마일스톤 | 범위 | 산출물(Deliverables) | 예상 노력 |
|---|---|---|---|
| MVP | 로컬 FS 스킬 인덱스 + system prompt 주입 + 선택 스킬 본문 로딩(지연) | `skills.py`(메타 파서/로더), `agents.py` 훅, unit tests, README 섹션 | 1.0–1.5 pw |
| v1 | 비-FS 환경 지원(옵션 Tool), 권한/신뢰 플래그, E2E 테스트 | `SkillActivateTool`, `SkillResourceTool`, 런타임 옵션, SECURITY/CONTRIBUTING 업데이트, E2E tests | 1.5–2.5 pw |
| v2 | 라우터 고도화(BM25 옵션), CLI(scan/validate), 캐시/무효화 | CLI 구현, router 개선, 성능 지표(log/monitor), 문서 템플릿 | 2.0–3.0 pw |

### 리스크 분석과 롤백 전략

- **리스크: 프롬프트 길이 증가로 성능/비용 악화**  
  - 완화: 메타데이터 아주 짧게 + 상한(30~50) + “skills disabled by default” 플래그로 점진 롤아웃  
- **리스크: 서드파티 스킬/리소스로 인한 prompt injection/데이터 유출**  
  - 완화: tool과 동일한 trust 플래그(기본 거부), sandbox 권장, 문서/정적 린트  
- **리스크: agents.py 수정으로 1.25의 steps 전환과 충돌**  
  - 완화: system prompt 생성 경로에만 국소 변경, steps/memory 구조는 건드리지 않기 (agents.py deprecation 고려) citeturn2view5turn2view0  
- **롤백**: 기능 플래그(예: `enable_skills=False` 기본) + 코드 경로를 분리하여, 문제 발생 시 플래그/주입 훅만 제거하면 되도록 설계

## Code examples

아래 코드는 smolagents 스타일(dataclass, strict validation, 최소 추상화)을 따르는 “간결한” 예시다. 실제 구현 위치는 주석에 명시한다.

### `src/smolagents/skills.py` (신규) — 메타 파싱/인덱스/지연 로딩

```python
# src/smolagents/skills.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    location: str  # "repo" | "user" | "hub"
    skill_dir: Path
    version: str | None = None


@dataclass(frozen=True)
class SkillBody:
    meta: SkillMeta
    body_markdown: str
    tree: tuple[str, ...]  # relative paths under skill_dir


class SkillError(RuntimeError):
    pass


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise SkillError("Missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillError("Invalid frontmatter block")
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return fm, body


def scan_skill_dirs(skill_roots: list[tuple[str, Path]]) -> list[SkillMeta]:
    metas: list[SkillMeta] = []
    for location, root in skill_roots:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            fm, _body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
            if "name" not in fm or "description" not in fm:
                continue
            meta = fm.get("metadata") or {}
            version = str(meta.get("version")) if isinstance(meta, dict) and meta.get("version") else None
            metas.append(
                SkillMeta(
                    name=str(fm["name"]),
                    description=str(fm["description"]),
                    location=location,
                    skill_dir=skill_md.parent,
                    version=version,
                )
            )
    # deterministic
    return sorted(metas, key=lambda m: (m.location, m.name))


def load_skill_body(meta: SkillMeta, max_chars: int = 30_000) -> SkillBody:
    skill_md = meta.skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    _fm, body = _split_frontmatter(text)

    if len(body) > max_chars:
        body = body[:max_chars] + "\n\n[TRUNCATED]"

    tree = tuple(
        str(p.relative_to(meta.skill_dir))
        for p in meta.skill_dir.rglob("*")
        if p.is_file() and p.name != "SKILL.md"
    )
    return SkillBody(meta=meta, body_markdown=body, tree=tree)
```

### `src/smolagents/agents.py` (수정) — system prompt에 skill index 주입

```python
# src/smolagents/agents.py (inside MultiStepAgent or prompt init function)
# Place near initialize_system_prompt() implementation.

from .skills import scan_skill_dirs

def format_skills_markdown_index(skill_metas, limit: int = 40) -> str:
    lines = ["Available skills (metadata only):"]
    for m in skill_metas[:limit]:
        ver = f"@{m.version}" if m.version else ""
        lines.append(f"- {m.name}{ver}: {m.description} (loc={m.location})")
    return "\n".join(lines)

# In system prompt builder:
# skill_metas = scan_skill_dirs([...])  # repo/user roots computed from cwd & home
# system_prompt += "\n\n" + format_skills_markdown_index(skill_metas)
```

### `src/smolagents/skill_tools.py` (신규, v1 옵션) — 비-FS 환경용 Tool

```python
# src/smolagents/skill_tools.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from .skills import load_skill_body, scan_skill_dirs, SkillError
from .tools import Tool


class ActivateSkillTool(Tool):
    name = "activate_skill"
    description = "Load the SKILL.md body (without metadata) and file tree for a named skill."
    inputs = {"name": {"type": "string", "description": "Skill name"}}
    output_type = "any"
    output_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "body": {"type": "string"},
            "tree": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "body"],
    }

    def __init__(self, skill_roots: list[tuple[str, Path]]):
        super().__init__()
        self._skill_roots = skill_roots

    def forward(self, name: str) -> dict[str, Any]:
        metas = scan_skill_dirs(self._skill_roots)
        meta = next((m for m in metas if m.name == name), None)
        if meta is None:
            return {"name": name, "body": "", "tree": [], "error": f"SkillNotFound: {name}"}

        try:
            body = load_skill_body(meta)
            return {"name": name, "body": body.body_markdown, "tree": list(body.tree)}
        except SkillError as e:
            return {"name": name, "body": "", "tree": [], "error": f"SkillLoadError: {e}"}
```

## PR structure & review guidance

### 권장 PR/브랜치 분할(리뷰 부담 최소화)

1) **PR #1 (MVP Core)**  
   - `src/smolagents/skills.py` 신규  
   - `agents.py`의 system prompt 주입 훅(최소 변경)  
   - `tests/test_skills_parser.py`(unit)  
   - README에 “Skills (experimental)” 섹션

2) **PR #2 (Tool fallback + security docs)**  
   - `src/smolagents/skill_tools.py` 신규  
   - `default_tools.py` 또는 agent init 경로에 “스킬 존재 시에만 tool 주입” 로직  
   - SECURITY/CONTRIBUTING 업데이트(서드파티 스킬 신뢰 모델)

3) **PR #3 (CLI + router 개선)**  
   - `cli.py`에 `smolagent skills scan/validate`  
   - router(BM25 옵션) + 테스트

### 라벨/체크리스트(제안)

- Labels: `feature`, `docs`, `security`, `tests`, `breaking-change`(해당 시)  
- PR 체크리스트(요약):
  - [ ] `make quality` 통과(ruff check/format) citeturn2view3turn2view2  
  - [ ] `make test` 통과(pytest) citeturn2view3  
  - [ ] Skills 기능 플래그 기본 OFF 또는 “스킬 존재 시에만 활성”  
  - [ ] Hub/remote skills는 trust 플래그 없이 로드 불가(툴과 동일한 모델) citeturn3view0  
  - [ ] 샌드박스 권고 문구/문서 반영(SECURITY.md와 일관) citeturn2view4  

### 리뷰 요청 가이드(“repo owners” 기반 추정 + 명시적 가정)

- **가정**: CODEOWNERS 파일을 확인할 수 없었으므로(요청 시 API 제한/파일 부재 가능), pyproject authors 및 README의 BibTeX/저자 정보를 기반으로 리뷰 요청 후보를 제안한다. (pyproject.toml L0-L1, repo root BibTeX 구간) citeturn2view0turn0view0  
- 최우선 리뷰 요청 후보:
  - Aymeric Roucher (pyproject authors) citeturn2view0  
  - 그리고 Hugging Face smolagents 코어 팀(원 저장소 소유 조직이 entity["company","Hugging Face","ai company"] 임을 전제로) citeturn0view0  

---

### 결론적으로, “smolagents스러운 Skills”의 구현 원칙

1) **agents.py의 큰 구조(steps/memory/tool dict)를 바꾸지 말고**, system prompt 생성 경로에 “짧은 메타 인덱스 주입”만 추가한다. citeturn2view5  
2) **파일시스템 접근 가능 시에는 CodeAgent의 파이썬 실행을 기본 경로로** 활용하여 “새로운 도구/프로토콜”을 최소화한다. citeturn0view0turn2view5  
3) **비-FS 환경만을 위해 Skill Tools를 선택적으로 주입**하고, Tool 인터페이스(`inputs/output_schema`)와 trust 모델을 엄격히 따른다. citeturn3view0  
4) Hub 공유는 강력하나 위험하므로, smolagents의 기존 원칙(검토 + trust 플래그)을 그대로 Skills에 이식해 보안/철학 일관성을 유지한다. citeturn3view0turn2view4