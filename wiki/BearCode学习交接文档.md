# BearCode 学习交接文档

## 目标与讲解偏好

用户正在通过 VS Code 断点逐步学习 BearCode 的启动流程、Agent Loop、Tools、MCP、Skills 和 Memory。讲解函数时优先先讲整体流程，再用一个具体入参展示关键变量值、条件判断和返回值。避免一开始陷入过多实现细节。

## 当前仓库状态

- 工作目录：`/Users/yuanyl/Downloads/源码+简历+测评+全量文档/BearCode`
- 当前分支：`main`
- `origin`：`https://github.com/yuyuanlang136-eng/Multi-Scenario-Agent.git`
- 原项目远程保留为 `upstream`：`git@github.com:Biscuit-AI531/BearCode.git`
- Python 虚拟环境已重建为项目根目录下的 `.venv`，项目可以启动。
- VS Code 调试配置位于 `.vscode/`，包含完整启动、REPL 断点和 one-shot 三种配置。

最近完成的提交：

- `985c187 fix: resolve API protocol from config source`
- `1132c9d chore: add VS Code debug configurations`
- `aa69aa2 docs: clarify skill lifecycle in agent flow`

## 已理解的主调用链

```text
python -m agents.main
  -> main()
  -> 解析 CLI 和环境变量
  -> 创建 Agent
  -> asyncio.run(run_repl(agent)) 或 asyncio.run(run_one_shot(agent, prompt))
  -> agent.chat(user_message)
  -> _chat_openai() 或 _chat_anthropic()
  -> _call_openai_stream() 或 _call_anthropic_stream()
  -> LLM 返回文本或 tool call
  -> 执行工具并把 tool result 回写消息历史
  -> 再次调用 LLM，直到没有 tool call
```

`run_repl()` 循环读取用户输入，每次调用一次 `chat()`。CLI one-shot 使用 `run_one_shot()`，它只调用一次 `chat()`。`run_once()` 主要供子 Agent 使用，因为它会收集并返回回答文本和本轮 Token，而 `chat()` 本身返回 `None`。

## `chat()` 的整体职责

1. 主 Agent 首次对话时初始化 MCP Server，并合并 MCP 工具。
2. 保留原始用户输入，并根据当前 query 召回相关 Skills。
3. 取出上一轮待学习窗口，把本轮输入作为对上一轮回答的反馈。
4. 根据 `use_openai` 选择 OpenAI 或 Anthropic Agent Loop。
5. 等待完整的“LLM -> 工具 -> LLM”循环结束，并收集流式回答文本。
6. 后台统计本轮召回的 Skill 是否相关、是否真正被采用。
7. 从第二轮开始，后台判断上一轮对话是否值得沉淀为 Skill。
8. 暂存本轮对话，等待下一轮反馈；打印结束线并自动保存 Session。

## MCP 已确认结论

`.mcp.json` 中的 `context7` 和 `playwright` 是两个 MCP Server，不是两个 Tool。每个 Server 启动后通过 `tools/list` 公布多个工具。`McpManager` 把各 Server 返回的工具合并，并转换为 `mcp__<server>__<tool>` 名称。模型调用这种工具时，Runtime 再按名称路由回对应 Server。

## Skill 加载、召回和执行

System Prompt 中会列出所有 Skill 的索引信息：名称、描述和 `when_to_use`，不会放入完整 `SKILL.md` 正文。

每轮 `chat()` 还会根据 query 做一次本地 BM25 风格召回：评分时使用 Skill 名称、描述、`when_to_use` 和正文前 2500 字符，最多取 3 个。注入当前用户消息的 `<retrieved_skills>` 只包含名称、分数、来源、描述和可选的 `when_to_use`，不包含完整正文。

模型判断某个 Skill 确实适用后调用 `skill` 工具。此时 `execute_skill()` 才加载完整正文；`inline` Skill 把正文作为 tool result 返回主 Agent，`fork` Skill 把正文作为子 Agent 的自定义 System Prompt。

当前实现同时在 System Prompt 列出全量 Skill 索引，又向用户消息注入 Top 3 摘要，存在一定重复。召回的额外价值是按当前 query 排序、使用正文参与匹配、记录使用统计，以及为 Skill 进化提供已有 Skill 引用。

## Skill 自动沉淀框架

Skill 自进化不会训练模型或修改模型权重，只会创建或更新 `SKILL.md`。

```text
第 N 轮结束
  -> 暂存第 N 轮用户输入和回答

第 N+1 轮开始
  -> 取出第 N 轮窗口
  -> 把第 N+1 轮用户输入作为后续反馈

第 N+1 轮主要回答结束
  -> 后台 Skill Extractor 提取至多一个可复用候选
  -> Skill Manager 对比已有 Skills
  -> 决定 add / merge / discard
  -> 权限允许时创建或更新 SKILL.md
```

因此第一轮不会执行“上一轮 Skill 沉淀”；从第二轮开始才可能判断上一轮。普通 one-shot 没有下一轮反馈，通常不会自动沉淀当前轮。

后台写入只有在 `acceptEdits` 或 `bypassPermissions` 模式自动允许；`default` 模式的后台写入会被拒绝，`plan` 模式跳过在线进化。详细实现尚未逐行学习，下一次从 `agents/online_skill_evolution.py` 继续。

## Persistent Memory 保存与召回

默认主 Agent 的 System Prompt 一直包含 Memory System 说明和 `MEMORY.md` 索引。使用自定义 System Prompt 的子 Agent 不一定包含它，子 Agent 也跳过自动 Memory 召回。

长期 Memory 目前没有“每轮结束后自动提取”的后台流程。主 LLM 根据 Memory System Prompt 判断信息值得长期保存时，调用 `write_file` 创建单独的 Memory Markdown 文件。程序随后自动更新 `MEMORY.md`。

```text
~/.BearCode/projects/<project_hash>/memory/
  MEMORY.md                         # 索引，不是全部记忆正文
  user_<name>.md                    # 用户信息或偏好
  feedback_<name>.md                # 用户纠正和反馈
  project_<name>.md                 # 项目背景与决定
  reference_<name>.md               # 外部参考
```

自动召回发生在 `_chat_openai()` / `_chat_anthropic()` 内：Runtime 启动一个辅助 LLM 查询，让它根据文件名和描述返回最多 5 个 Memory 文件名；Python 随后直接读取文件正文，并以 `<system-reminder>` 追加到当前用户消息。这个过程不会让主 LLM 输出 `read_file` 工具调用。

当前异步实现有一个需要后续关注的时序特点：预取任务刚创建后，Agent Loop 立即检查它是否完成。如果第一次主模型请求直接返回最终答案，没有进入下一轮工具循环，召回结果可能来不及注入。

## 三类容易混淆的记忆

- Persistent Memory：用户偏好、项目事实和历史决定；每条一个 Markdown 文件，`MEMORY.md` 是索引。
- Session：每轮自动把完整消息历史保存到 `~/.bear-code/sessions/<session-id>.json`，供 `--resume` 使用。
- Folded Session Memory：上下文过长时把历史压缩成结构化状态，保存到项目的 `.bear/sessions/*.folded-memory.*`，用于继续当前长任务。

## 已掌握的调试操作

- F5：Continue，运行到下一个断点。
- F10：Step Over，执行当前行，不进入函数内部。
- F11：Step Into，进入当前行将调用的函数。
- Shift+F11：Step Out，执行完当前函数并返回调用者。
- Watch 对字符串显示 `repr`，换行显示为 `\n`；在 Debug Console 使用 `print(value)` 查看真实换行。
- 调试器不能倒退到已经执行过的代码；需要 Restart，或提前设置目标断点后按 F5。

## 下一次建议阅读顺序

1. 先整体阅读 `Agent._run_online_skill_evolution()` 和 `_run_skill_usage_tracking()`。
2. 阅读 `online_ingest()`，理解“提取候选 -> 维护 Skill 集 -> 记录来源”。
3. 阅读 `extract_online_skill_candidate()`，观察传给辅助 LLM 的 system、payload 和返回 JSON。
4. 阅读 `maintain_online_skill_candidate()`，理解 exact match、相似召回和 add/merge/discard。
5. 再阅读 Memory：`build_memory_prompt_section()`、`start_memory_prefetch()`、`select_relevant_memories()` 和注入逻辑。
6. 最后回到 `_chat_anthropic()` 或 `_chat_openai()`，完整跟一次“用户消息 -> Memory -> LLM -> 工具 -> LLM”。

## 下一次对话的起始问题

请从 Skill 自动沉淀开始，只先讲整体框架，然后带我调试 `Agent._run_online_skill_evolution()`。每解释一个函数，给出一个具体入参、关键中间变量值、条件判断结果和最终返回值。
