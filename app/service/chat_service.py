import asyncio
import json
import logging
import sys
import os
import time
import hashlib
from uuid import uuid4

# 初始化 Agent 和 Graph
AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.workflow.graph_manager import AgentGraphManager
from core.workflow.checkpointer import close_checkpointer, create_redis_checkpointer
from core.memory.memory_manager import MemoryManager
from app.infra.cache import semantic_cache

# Global variables for graph and memory
graph = None
checkpointer = None
memory = None
extraction_llm = None
logger = logging.getLogger("clinical_cds.chat")

MIN_CLINICAL_QUERY_LENGTH = 4
CHAT_TIMEOUT_SECONDS = 210
SHORT_QUERY_RESPONSE = (
    "请输入更完整的临床问题或患者信息，例如症状、持续时间、严重程度、既往用药、"
    "量表分数或需要审查的药物组合。当前输入过短，系统不会进入诊疗推理流程。"
)

# 长期记忆提取：每 N 轮对话后台触发一次
EXTRACT_EVERY_N_TURNS = 5
_turn_counters: dict[tuple[str, str], int] = {}
# 持有后台任务强引用，避免任务被垃圾回收中断
_bg_extract_tasks: set[asyncio.Task] = set()

async def init_agent_system():
    global graph, memory, extraction_llm, checkpointer
    if graph is None:
        logger.info("event=agent_system_init step=graph_start")
        from config import get_settings
        settings = get_settings()

        # 会话级状态：LangGraph Checkpoint + Redis（不可用时图退化为无状态）
        checkpointer = await create_redis_checkpointer(settings.redis_url)
        graph = AgentGraphManager().build_graph(checkpointer=checkpointer)

        logger.info("event=agent_system_init step=memory_start")
        memory = MemoryManager(
            milvus_host=settings.milvus_host,
            milvus_port=settings.milvus_port,
            milvus_api_key=settings.milvus_api_key,
            embedding_api_key=settings.get_embedding_api_key(),
        )
        await memory.initialize()
        extraction_llm = ChatOpenAI(**settings.get_model_config(), temperature=0)
        await semantic_cache.initialize()
        logger.info("event=agent_system_init step=complete")

async def shutdown_agent_system():
    """释放 Agent 系统持有的连接（FastAPI lifespan 关闭时调用）。"""
    global graph, checkpointer
    await close_checkpointer(checkpointer)
    if memory is not None:
        await memory.close()
    graph = None
    checkpointer = None

async def _extract_long_term_context(user_id: str, query: str, session_id: str = 'default_session') -> str:
    """检索 Milvus 长期记忆中的临床要点（近期历史由 checkpoint 自动携带）。"""
    if not (memory and memory.long_term.available):
        return ""
    prefs = await memory.load_preferences(_user_fact_namespace(user_id, session_id), query)
    if not prefs:
        return ""
    lines = ["【用户陈述的历史背景；不是当前知识版本的证据或系统确认的诊断】:"]
    lines.extend(f"- {p}" for p in prefs)
    return "\n".join(lines)

def _format_conversation(messages: list[BaseMessage]) -> str:
    """将 checkpoint 消息历史渲染为提取器所需的 role: content 文本。"""
    parts = []
    for m in messages:
        content = getattr(m, "content", "")
        if not content:
            continue
        if isinstance(m, SystemMessage):
            role = "System"
        elif isinstance(m, HumanMessage):
            role = "User"
        else:
            role = "Assistant"
        parts.append(f"{role}: {content}")
    return "\n".join(parts)

def session_config(user_id: str, session_id: str) -> dict:
    """The saver indexes thread_id, not user_id. Never reopen an unscoped legacy thread."""
    key = json.dumps([user_id, session_id], ensure_ascii=False, separators=(',', ':'))
    return {'configurable': {'thread_id': 'case_v2_' + hashlib.sha256(key.encode()).hexdigest(),
                             'user_id': user_id, 'session_id': session_id}}


def _user_fact_namespace(user_id, session_id='default_session'):
    # A new case must not inherit another patient's facts or legacy doctor-wide memory.
    return 'casefacts_v2_' + session_config(user_id, session_id)['configurable']['thread_id']

async def _cache_owner(user_id,config,binding,memory_context):
    history=[]
    if checkpointer is not None:
        try:
            snapshot=await graph.aget_state(config)
            values=snapshot.values
            same=values.get('history_knowledge_identity')==binding.identity
            messages=values.get('messages',[]) if same else list(values.get('user_messages',[]))+list(values.get('messages',[]))
            seen=set()
            for m in messages:
                if not same and not isinstance(m,HumanMessage):continue
                key=m.id or str(m.content)
                if key in seen:continue
                seen.add(key);history.append((m.type,m.content))
        except Exception:
            # Unknown context cannot safely share a cached answer, including another failed read.
            history=[('unavailable',uuid4().hex)]
    payload=json.dumps([user_id,binding.identity,history,memory_context],ensure_ascii=False,sort_keys=True)
    return 'turn_'+hashlib.sha256(payload.encode()).hexdigest()

async def _record_cache_hit_turn(config: dict, query: str, answer: str, binding=None) -> None:
    """语义缓存命中不经过图执行，手动把该轮写入 checkpoint 保持多轮连续。"""
    if checkpointer is None:
        return
    try:
        message=HumanMessage(content=query,id=uuid4().hex)
        await graph.aupdate_state(
            config,
            {"messages": [message, AIMessage(content=answer,additional_kwargs={'knowledge_binding':binding.metadata()} if binding else {})],
             "user_messages": [message]},
        )
        logger.info("event=cache_hit_state_recorded")
    except Exception as exc:
        logger.warning("Failed to record cache-hit turn into checkpoint: %s", exc)

def _is_insufficient_query(query: str) -> bool:
    normalized = "".join(query.strip().split())
    return len(normalized) < MIN_CLINICAL_QUERY_LENGTH

async def _stream_chat(query: str, user_id: str, session_id: str):
    request_start = time.perf_counter()
    last_step = request_start
    from core.graph.runtime_version import resolve_binding
    try:
        binding=await asyncio.to_thread(resolve_binding)
    except Exception:
        logger.exception('Knowledge version resolution failed')
        yield 'data: '+json.dumps({'error':'knowledge_version_unavailable','content':'当前知识版本不可用，请检查版本管理后重试。'},ensure_ascii=False)+'\n\n'
        yield 'data: {"done": true}\n\n'
        return

    def emit_sse(payload: dict, kind: str) -> str:
        payload['knowledge_version']=binding.version
        payload['knowledge_name']=binding.name
        payload['knowledge_checksum']=binding.checksum
        logger.info(
            "event=sse_emit user_id=%s session_id=%s kind=%s total=%.3fs",
            user_id,
            session_id,
            kind,
            time.perf_counter() - request_start,
        )
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def log_step(name: str) -> None:
        nonlocal last_step
        now = time.perf_counter()
        logger.info(
            "event=chat_step user_id=%s session_id=%s step=%s elapsed=%.3fs total=%.3fs",
            user_id,
            session_id,
            name,
            now - last_step,
            now - request_start,
        )
        last_step = now

    logger.info(
        "event=chat_request_start user_id=%s session_id=%s query_chars=%d",
        user_id,
        session_id,
        len(query),
    )
    yield emit_sse({"status": "accepted", "content": "已接收病例，开始分析..."}, "status")

    config = session_config(user_id, session_id)
    should_record_turn = True

    if _is_insufficient_query(query):
        response_text = SHORT_QUERY_RESPONSE
        should_record_turn = False
        logger.info("event=chat_short_query user_id=%s session_id=%s", user_id, session_id)
        log_step("local_input_validation")
        yield emit_sse({"agent": "input_validation", "content": response_text}, "content")
    else:
        memory_context = await _extract_long_term_context(user_id, query, session_id)
        turn_cache=await semantic_cache.for_knowledge(binding.identity)
        cache_owner=await _cache_owner(user_id,config,binding,memory_context)
        yield emit_sse({"status": "semantic_cache_check", "content": "正在检查语义缓存..."}, "status")
        cache_hit = await turn_cache.get_cache(query, cache_owner)
        log_step("semantic_cache_check")
        if cache_hit:
            response_text = cache_hit["answer"]
            logger.info(
                "event=semantic_cache_hit user_id=%s session_id=%s level=%s distance=%.4f",
                user_id,
                session_id,
                cache_hit["level"],
                cache_hit["distance"],
            )
            yield emit_sse({"agent": "semantic_cache", "content": response_text,"cache_hit":True}, "content")
            await _record_cache_hit_turn(config, query, response_text,binding)
        else:
            logger.info("event=agent_workflow_start user_id=%s session_id=%s", user_id, session_id)
            yield emit_sse({"status": "memory_context_extract", "content": "正在提取会话记忆..."}, "status")
            log_step("memory_context_extract")

            yield emit_sse({"status": "agent_workflow_start", "content": "正在进入多智能体分析..."}, "status")
            full_response = ""
            current_agent = None
            last_content_agent = None

            # 每轮只传新消息，历史由 checkpoint 的 add_messages reducer 累积
            message=HumanMessage(content=query,id=uuid4().hex)
            state = {
                "messages": [message],
                "user_messages": [message],
                "knowledge_binding":binding.metadata(),
                "user_id": user_id,
                "session_id": session_id,
                "memory_context": memory_context,
                "next_agent": "",
                "metadata": {}
            }

            async for stream_mode, data in graph.astream(
                state, config=config, stream_mode=["updates", "custom"]
            ):
                if stream_mode == "custom":
                    if data.get("event") == "start":
                        current_agent = data["agent"]
                        yield emit_sse(
                            {"status": "agent_node_start", "agent": current_agent},
                            "status",
                        )
                    elif data.get("event") == "tool_call":
                        tool_name = data.get("tool", "")
                        yield emit_sse(
                            {"status": "agent_tool_call", "agent": current_agent, "content": f"正在调用 {tool_name}..."},
                            "status",
                        )
                    elif data.get("event") == "tool_done":
                        yield emit_sse(
                            {"status": "agent_tool_done", "agent": current_agent, "content": "工具查询完成，正在生成分析..."},
                            "status",
                        )
                    elif data.get('event') == 'consistency_check':
                        yield emit_sse({'status':'clinical_consistency_check','agent':current_agent,
                                        'content':'正在核对病程、已知信息与诊断条件...'},'status')
                    elif "chunk" in data:
                        content_agent=data.get('agent',current_agent)
                        chunk=data['chunk']
                        if full_response and content_agent!=last_content_agent and not full_response.endswith('\n\n'):
                            chunk='\n\n'+chunk
                        full_response += chunk
                        last_content_agent=content_agent
                        yield emit_sse(
                            {"agent": content_agent, "content": chunk},
                            "content",
                        )

                elif stream_mode == "updates":
                    for node_name, node_output in data.items():
                        logger.info("event=agent_update user_id=%s session_id=%s node=%s", user_id, session_id, node_name)
                        yield emit_sse(
                            {
                                "status": "agent_node_complete",
                                "agent": node_name,
                                "content": f"{node_name} 已完成，正在整理结果...",
                            },
                            "status",
                        )

            log_step("agent_workflow")
            response_text = full_response

            # 推理结果写入语义缓存，供后续相似问题直接命中
            if turn_cache.available and response_text:
                try:
                    await turn_cache.set_cache(query, response_text, user_id=cache_owner)
                except Exception as exc:
                    logger.warning("semantic_cache set_cache failed: %s", exc)

    # 周期性长期记忆提取：从 checkpoint 历史提取临床要点（后台执行，不阻塞 SSE）
    if should_record_turn and memory and memory.long_term.available and extraction_llm is not None:
        counter_key = (user_id, session_id)
        _turn_counters[counter_key] = _turn_counters.get(counter_key, 0) + 1
        if _turn_counters[counter_key] % EXTRACT_EVERY_N_TURNS == 0:
            task = asyncio.create_task(
                _extract_long_term_memory(config, user_id)
            )
            _bg_extract_tasks.add(task)
            task.add_done_callback(_bg_extract_tasks.discard)
            logger.info(
                "event=long_term_extract_scheduled user_id=%s session_id=%s turn=%d",
                user_id, session_id, _turn_counters[counter_key],
            )

    yield emit_sse({"done": True}, "done")
    log_step("sse_complete")

async def _extract_long_term_memory(config: dict, user_id: str) -> None:
    """后台任务：读取 checkpoint 会话历史并提取临床要点到 Milvus。"""
    try:
        snapshot = await graph.aget_state(config)
        messages = list(snapshot.values.get('user_messages') or snapshot.values.get("messages", []))
        messages = [m for m in messages if isinstance(m,HumanMessage)]
        conversation = _format_conversation(messages)
        if conversation.strip():
            case_id = config.get('configurable', {}).get('session_id', 'default_session')
            await memory.extract_from_conversation(_user_fact_namespace(user_id, case_id), conversation, extraction_llm)
    except Exception as exc:
        logger.warning("Long-term memory extraction failed: %s", exc)


async def stream_chat(query: str,user_id: str,session_id: str):
    """Report failed streams explicitly, without caching a partial answer."""
    metadata={}
    try:
        async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
            async for event in _stream_chat(query,user_id,session_id):
                payload=json.loads(event.removeprefix('data: ').strip())
                metadata={k:v for k,v in payload.items() if k.startswith('knowledge_')}
                yield event
    except asyncio.CancelledError:raise
    except TimeoutError:
        logger.warning('event=chat_timeout user_id=%s session_id=%s',user_id,session_id)
        yield 'data: '+json.dumps(dict(metadata,error='inference_timeout',content='本轮分析超时，请缩小问题范围后重试。'),ensure_ascii=False)+'\n\n'
        yield 'data: '+json.dumps(dict(metadata,done=True,failed=True))+'\n\n'
    except Exception:
        logger.exception('Chat stream failed')
        yield 'data: '+json.dumps(dict(metadata,error='inference_failed',content='本轮分析未完成，请稍后重试。'),ensure_ascii=False)+'\n\n'
        yield 'data: '+json.dumps(dict(metadata,done=True,failed=True))+'\n\n'
