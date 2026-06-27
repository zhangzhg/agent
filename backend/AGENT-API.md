以下是为您提取的星辰智能体平台工作流编排对话型应用 API 的详细接口文档，包含各接口的请求参数和响应字段详情，已整理为 Markdown 格式。
# 星辰智能体平台 - 工作流编排对话型应用 API 详细文档
## 基础信息
* **Base URL**: `https://agent.teleai.com.cn/v1`
* **鉴权方式**: 使用 `API-Key` 鉴权。
* **Header 要求**: 所有请求需在 HTTP Header 中包含：
  ```http
  Authorization: Bearer {API_KEY}
  ```
---
## 1. 发送对话消息
**POST** `/chat-messages`
创建会话消息，支持流式和阻塞模式。
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `query` | string | 是 | 用户输入/提问内容。 |
| `input_data` | object | 否 | 允许传入 App 定义的各变量值（键值对），默认 `{}`。 |
| `mode` | string | 是 | 模式：`streaming` (流式) 或 `blocking` (阻塞)。 |
| `user` | string | 是 | 用户标识，需在应用内唯一。 |
| `conversation_id` | string | 否 | 会话 ID，基于之前聊天记录继续对话时需传入。 |
| `files` | array[object] | 否 | 文件列表。 |
| `files[].type` | string | 是 | 文件类型：`document`, `image`, `audio`, `video`。 |
| `files[].transfer_method` | string | 是 | 传递方式：`remote_url` (图片地址), `local_file` (上传文件)。 |
| `files[].url` | string | 否 | 图片地址（仅 `remote_url` 时必填）。 |
| `files[].upload_file_id` | string | 否 | 上传文件 ID（仅 `local_file` 时必填）。 |
### Response (阻塞模式 - ChatCompletionResponse)
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `message_id` | string | 消息唯一 ID。 |
| `conversation_id` | string | 会话 ID。 |
| `mode` | string | App 模式，固定为 `advanced-chat`。 |
| `answer` | string | 完整回复内容。 |
| `metadata` | object | 元数据（包含 `usage` 模型用量信息和 `retriever_resources` 引用列表）。 |
| `created_at` | int | 消息创建时间戳，如：1705395332。 |
| `check_content_failed` | string | 内容合规性检测失败信息。 |
| `message` | string | 兜底文案（若展示为兜底文案，则输出为违规内容）。 |
### Response (流式模式 - ChunkChatCompletionResponse)
返回 `text/event-stream`，以 `data: ` 开头的流式块，根据 `event` 不同结构不同：
| Event 名称 | 描述 | 核心字段 |
| :--- | :--- | :--- |
| `workflow_started` | workflow 开始执行 | `task_id`, `workflow_run_id`, `data` (包含 `workflow_id`, `created_at` 等) |
| `node_started` | node 开始执行 | `task_id`, `workflow_run_id`, `data` (包含 `node_id`, `node_type`, `title`, `inputs` 等) |
| `node_finished` | node 执行结束 | `task_id`, `workflow_run_id`, `data` (包含 `node_id`, `status`, `outputs`, `elapsed_time` 等) |
| `workflow_finished` | workflow 执行结束 | `task_id`, `workflow_run_id`, `data` (包含 `status`, `outputs`, `total_tokens` 等) |
| `message` | LLM 返回文本块事件 | `message_id`, `conversation_id`, `answer` (文本块内容), `created_at` |
| `message_file` | 文件事件 | `id`, `type`, `belongs_to` (仅 assistant), `url`, `conversation_id` |
| `message_end` | 消息结束事件 | `message_id`, `conversation_id`, `metadata` (含 `usage` 和 `retriever_resources`) |
| `message_replace`| 消息内容替换事件 | `message_id`, `conversation_id`, `answer` (替换内容), `created_at` |
| `error` | 异常事件 | `message_id`, `status` (HTTP状态码), `code`, `message` (错误消息) |
| `ping` | 保活事件 | 每 10s 一次。 |
| `check_failed` | 内容合规检测失败 | `check_failed_msg`, `message_id`, `conversation_id` |
---
## 2. 上传文件
**POST** `/files/upload`
上传文件并在发送消息时使用。
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `file` | file | 是 | 要上传的文件。 |
| `user` | string | 是 | 用户标识，需与发送消息接口的 `user` 一致。 |
### Response (UploadResponse)
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | uuid | 文件 ID。 |
| `name` | string | 文件名。 |
| `size` | int | 文件大小（byte）。 |
| `extension` | string | 文件后缀。 |
| `mime_type` | string | 文件 mime-type。 |
| `created_by` | uuid | 上传人 ID。 |
| `created_at` | timestamp | 上传时间戳。 |
---
## 3. 停止响应
**POST** `/chat-messages/:task_id/stop`
停止流式模式的响应。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `task_id` | string | 是 | 任务 ID，可在流式返回的 Chunk 中获取。 |
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识，需与发送消息接口的 `user` 一致。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `result` | string | 固定返回 `success`。 |
---
## 4. 消息反馈（点赞/点踩）
**POST** `/messages/:message_id/feedbacks`
对消息进行反馈。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `message_id` | string | 是 | 消息 ID。 |
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `rating` | string | 是 | `like` (点赞), `dislike` (点踩), `null` (撤销)。 |
| `label` | string | 否 | 点踩标签选项（仅 `dislike` 时填入）。可选：答非所问,有害/不安全,虛假信息,逻辑问题,格式问题,沒有帮助。 |
| `content` | string | 否 | 点踩原因自定义说明（仅 `dislike` 时填入）。 |
| `user` | string | 是 | 用户标识。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `result` | string | 固定返回 `success`。 |
---
## 5. 获取下一轮建议问题列表
**GET** `/messages/{message_id}/suggested`
获取基于当前消息的后续建议问题。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `message_id` | string | 是 | 消息 ID。 |
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `result` | string | 固定返回 `success`。 |
| `data` | array[string] | 建议问题列表。 |
---
## 6. 获取会话历史消息
**GET** `/messages`
滚动加载返回历史聊天记录（倒序）。
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `conversation_id` | string | 是 | 会话 ID。 |
| `user` | string | 是 | 用户标识。 |
| `lead_id` | string | 否 | 当前页第一条聊天记录的 ID，用于分页，默认 `null`。 |
| `limit` | int | 否 | 一次请求返回条数，默认 20。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `limit` | int | 返回条数。 |
| `has_more` | bool | 是否存在下一页。 |
| `data` | array[object] | 消息列表。 |
| `data[].id` | string | 消息 ID。 |
| `data[].conversation_id`| string | 会话 ID。 |
| `data[].inputs` | array[object] | 用户输入参数。 |
| `data[].query` | string | 用户输入/提问内容。 |
| `data[].answer` | string | 回答消息内容。 |
| `data[].message_files` | array[object] | 消息文件列表（包含 `id`, `type`, `url`, `belongs_to`）。 |
| `data[].created_at` | timestamp | 创建时间戳。 |
| `data[].feedback` | object | 反馈信息。 |
| `data[].retriever_resources`| array[object]| 引用和归属分段列表（包含 `position`, `dataset_id`, `document_name`, `score`, `content` 等）。 |
---
## 7. 获取会话列表
**GET** `/conversations`
获取当前用户的会话列表。
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识。 |
| `tail_id` | string | 否 | 当前页最后面一条记录的 ID，默认 `null`。 |
| `limit` | int | 否 | 返回条数。 |
| `pinned` | bool | 否 | `true` 只返回置顶，`false` 只返回非置顶。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `limit` | int | 返回条数。 |
| `has_more` | bool | 是否存在下一页。 |
| `data` | array[object] | 会话列表。 |
| `data[].id` | string | 会话 ID。 |
| `data[].name` | string | 会话名称。 |
| `data[].inputs` | array[object] | 用户输入参数。 |
| `data[].introduction` | string | 开场白。 |
| `data[].created_at` | timestamp | 创建时间戳。 |
---
## 8. 删除会话
**DELETE** `/conversations/:conversation_id`
删除指定会话。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `conversation_id` | string | 是 | 会话 ID。 |
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `result` | string | 固定返回 `success`。 |
---
## 9. 会话重命名
**POST** `/conversations/:conversation_id/name`
对会话进行重命名或自动生成标题。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `conversation_id` | string | 是 | 会话 ID。 |
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `conversation_name` | string | 否 | 名称。若 `auto_generate` 为 `true` 可不传。 |
| `auto_generate` | bool | 否 | 是否自动生成标题，默认 `false`。 |
| `user` | string | 是 | 用户标识。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | string | 会话 ID。 |
| `name` | string | 会话名称。 |
| `inputs` | array[object] | 用户输入参数。 |
| `introduction` | string | 开场白。 |
| `created_at` | timestamp | 创建时间戳。 |
---
## 10. 获取应用配置信息
**GET** `/parameters`
获取功能开关、输入参数名称、类型及默认值等配置。
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识。 |
### Response (ParametersResponse)
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `opening_statement` | string | 开场白。 |
| `suggested_questions` | array[string] | 开场推荐问题列表。 |
| `suggested_questions_after_answer`| object | 启用回答后给出推荐问题，含 `enabled` (bool)。 |
| `speech_to_text` | object | 语音转文本配置，含 `enabled` (bool)。 |
| `retriever_resource` | object | 引用和归属配置，含 `enabled` (bool)。 |
| `annotation_reply` | object | 标记回复配置，含 `enabled` (bool)。 |
| `user_input_form` | array[object] | 用户输入表单配置（如 `text-input`, `paragraph`, `select` 控件）。 |
| `file_upload` | object | 文件上传配置，如 `image` 设置（含大小限制等）。 |
| `system_parameters` | object | 系统参数，如 `image_file_size_limit`。 |
---
## 11. 获取应用 Meta 信息
**GET** `/meta`
获取工具 icon。
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `user` | string | 是 | 用户标识。 |
### Response
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `tool_icons` | object[string] | 工具图标映射表。Key 为工具名称，Value 可为图片 URL (string) 或对象 `{ background: "#252525", content: "😁" }`。 |
---
## 12. 信息采集节点提交回调
**POST** `/v1/workflow/{conversation_id}/{message_id}/{form_id}/submit`
作为工作流中信息采集节点的表单提交回调 API。
### Path 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `conversation_id` | string | 是 | 会话 ID。 |
| `message_id` | string | 是 | 消息 ID。 |
| `form_id` | string | 是 | 表单 ID。 |
### Query 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `sign` | string | 是 | 签名。 |
| `form_end_time` | string | 是 | 表单结束时间(时间戳)。 |
### Request Body 参数
| 名称 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `inputs` | object | 是 | 用户填写的表单信息（键值对，Key 为字段名，Value 为填写值或文件列表）。 |
| `form_end_time` | number | 是 | 表单结束时间(时间戳)。 |
| `user` | string | 是 | 用户标识，需与发送消息接口的 `user` 保持一致。 |
### Response (infoCollectionResponse)
| 名称 | 类型 | 描述 |
| :--- | :--- | :--- |
| `data` | object | 固定返回空对象 `{}`。 |
