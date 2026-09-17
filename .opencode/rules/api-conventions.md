# API 接口设计规范

> 适用范围：M9b 后端（FastAPI）与 M9a 前端消费的 HTTP API。契约依据 `docs/specs/M9b-management-backend.md` 与 `docs/contract.md` §12。

## 1. 通用约定

### 1.1 路由前缀

- 所有业务路由统一挂在 `/api` 下，资源名一律 **复数**。
- 嵌套资源用子路径，不用查询参数表达实体关系。

```
✅  GET    /api/trees                # 列表
✅  POST   /api/trees                # 创建
✅  GET    /api/trees/{tree_id}      # 查看
✅  POST   /api/trees/{tree_id}/check
✅  GET    /api/runs/{run_id}/state
✅  GET    /api/runs/{run_id}/report
```

### 1.2 响应包装

- **不**做统一包装层（如 `{code, data, message}`）。直接返回资源本体，错误交给 HTTP 状态码。
- 列表接口返回裸数组或带分页元数据的对象（见 §4）。

```
✅  GET /api/trees → 200  [ {"id": 1, "name": "登录流程"}, ... ]
❌  GET /api/trees → 200  {"code": 0, "data": [...], "message": "ok"}
```

### 1.3 命名

- 路径参数：`snake_case`（如 `run_id`）。
- JSON 字段：Python 侧用 Pydantic，默认 `snake_case`，不做 camelCase 转换——前后端统一 snake_case，省去映射层。

## 2. FastAPI 路由写法

### 2.1 路由分层

- 路由文件按资源组织：`autobranch/server/routers/trees.py`、`routers/runs.py`。
- 只做 HTTP 编排（参数校验 / 状态码 / 调用 service），业务逻辑放 service 层。

```python
# autobranch/server/routers/trees.py
from fastapi import APIRouter, Depends, HTTPException, status

from autobranch.server.schemas.tree import TreeCreate, TreeOut, TreeUpdate
from autobranch.server.services.trees import TreeService

router = APIRouter(prefix="/api/trees", tags=["trees"])


@router.get("", response_model=list[TreeOut])
def list_trees(service: TreeService = Depends()):
    return service.list_all()


@router.post("", response_model=TreeOut, status_code=status.HTTP_201_CREATED)
def create_tree(payload: TreeCreate, service: TreeService = Depends()):
    return service.create(payload)


@router.put("/{tree_id}", response_model=TreeOut)
def update_tree(tree_id: int, payload: TreeUpdate, service: TreeService = Depends()):
    tree = service.update(tree_id, payload)
    if tree is None:
        raise HTTPException(status_code=404, detail="tree not found")
    return tree
```

### 2.2 方法语义

| 方法 | 语义 | 成功状态码 |
|---|---|---|
| GET 列表 | 查询集合 | 200 |
| POST 创建 | 新建资源 | 201 |
| GET 单个 | 查询单个 | 200 |
| PUT | 全量替换 | 200 |
| PATCH | 部分更新 | 200 |
| DELETE | 删除 | 204（无 body）或 200 + 删除对象 |

## 3. Pydantic Schema 约定

### 3.1 分层

每个资源三类 schema，分别用于创建 / 更新 / 输出：

```python
# autobranch/server/schemas/tree.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TreeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(description="行为树文档 yaml 文本")


class TreeUpdate(BaseModel):
    name: str | None = None
    content: str | None = None


class TreeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
```

### 3.2 规则

- 输入 schema：显式声明 `Field` 约束（长度 / 范围 / 必填），让 FastAPI 自动返回 422。
- 输出 schema：只暴露客户端需要的字段，**不返回内部实现字段**（如 SQLAlchemy 引擎句柄、LLM 密钥）。
- 拒绝的类型用类型注解表达，不要靠手写 `if not isinstance(...)`。

```
✅  age: int = Field(ge=0, le=120)
❌  age: int  # 之后再手动校验范围
```

## 4. 列表与分页

- 小数据量直接返回数组；大数据量返回分页对象。

```python
class PageOut(BaseModel):
    items: list[TreeOut]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PageOut)
def list_trees(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), ...):
    ...
```

## 5. 错误处理

### 5.1 用 HTTPException，不用裸 raise

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="tree not found")
```

### 5.2 错误码分类（契约 §9.4 错误源分流）

| 场景 | 状态码 |
|---|---|
| 资源不存在 | 404 |
| 参数非法 | 422 |
| 文档清晰度校验失败 | 422（detail 返回 `CheckReport` 错误清单） |
| 执行中的 LLM 侧失败 / 程序侧失败 | 500 + `failure_reason`，由执行状态查询携带 |
| 并发 / 重复触发 | 409 |

### 5.3 业务异常 → 统一异常处理器

```python
# autobranch/server/errors.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

## 6. 执行 API 约定（M9b 特有）

- `POST /api/trees/{id}/run`：**异步触发**，立即返回 `run_id`，不阻塞等待执行完成。
- 前端通过 `GET /api/runs/{run_id}/state` 每秒轮询进度（契约 §12.4）。

```python
@router.post("/{tree_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_tree(tree_id: int, engine: Engine = Depends(...)):
    run_id = await engine.start_async(tree_id)
    return {"run_id": run_id}
```

## 7. 安全

- **永不**在响应或日志中输出 LLM api_key / token。密钥只读自配置文件或环境变量。
- 报告 / 截图文件接口 `GET /api/reports/{path}` 必须做路径白名单校验，防目录穿越。

```python
from pathlib import Path

REPORT_ROOT = Path("data/reports").resolve()


def safe_report_path(path: str) -> Path:
    target = (REPORT_ROOT / path).resolve()
    if not target.is_relative_to(REPORT_ROOT):
        raise HTTPException(status_code=400, detail="invalid report path")
    return target
```

## 8. Do's & Don'ts 速查

| Do ✅ | Don't ❌ |
|---|---|
| 资源复数名词路由，嵌套用子路径 | 动词式路由（`/api/getTree`、`/api/deleteTree`） |
| 直接返回资源本体 + HTTP 状态码 | 统一 `{code, data, message}` 包装 |
| 输入输出分开 Pydantic schema | 一个 schema 通吃输入输出 |
| 用类型注解 + `Field` 约束表达校验 | 手写 if/raise 校验参数 |
| 422 给 FastAPI 校验失败，404 给不存在 | 所有错误一律 500 |
| 执行接口异步触发返回 run_id | 执行接口同步阻塞到完成 |
| 响应字段 snake_case | 前后端各做一套 camelCase 映射 |
| 校验失败返回错误清单（可读 detail） | 返回晦涩异常堆栈 |