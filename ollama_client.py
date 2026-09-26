import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"


def chat(messages, temperature=0.7):
    res = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=300,
    )
    res.raise_for_status()
    return res.json()["message"]["content"]


def _history(history, limit=15):
    msgs = []
    for m in history[-limit:]:
        role = "assistant" if m["sender_type"] == "ai" else "user"
        prefix = "" if role == "assistant" else f"{m['sender_name']}: "
        msgs.append({"role": role, "content": prefix + m["content"]})
    return msgs


def _lang_rule(lang):
    if lang == "en":
        return "Always respond in English."
    return "必ず日本語で答えてください。"


def ai_explain(subject, title, blackboard, topic, history, lang="ja"):
    system = f"""You are an expert teacher assistant for a "{subject}" class titled "{title}".
{_lang_rule(lang)}
Keep it concise and classroom-appropriate."""
    user = f"""Current blackboard:
{blackboard or '(empty)'}

Requested topic: {topic or '(continue the blackboard)'}

Write a short supplementary explanation (150-300 chars equivalent) to append to the blackboard.
Use bullet points. Plain text only."""
    msgs = [{"role": "system", "content": system}]
    msgs.extend(_history(history))
    msgs.append({"role": "user", "content": user})
    return msgs


def ai_quiz(subject, title, blackboard, history, lang="ja"):
    system = f"""You are a teacher assistant for a "{subject}" class titled "{title}".
{_lang_rule(lang)}"""
    user = f"""Blackboard content:
{blackboard or '(empty)'}

Create one multiple-choice quiz question (4 options) based on this.
End with a line "Answer: X". Plain text only."""
    msgs = [{"role": "system", "content": system}]
    msgs.extend(_history(history))
    msgs.append({"role": "user", "content": user})
    return msgs


def ai_answer_question(subject, title, blackboard, question, history, lang="ja"):
    system = f"""You are a teacher assistant for a "{subject}" class titled "{title}".
{_lang_rule(lang)} Answer briefly (within ~150 chars equivalent)."""
    user = f"""Blackboard content:
{blackboard or '(empty)'}

Student question: {question}"""
    msgs = [{"role": "system", "content": system}]
    msgs.extend(_history(history, limit=6))
    msgs.append({"role": "user", "content": user})
    return msgs


def ai_class_reply(subject, title, blackboard, history, lang="ja", teaching_focus=""):
    focus_line = f"\nClass focus: {teaching_focus}" if teaching_focus else ""
    system = f"""You are an AI teacher for a "{subject}" class titled "{title}".{focus_line}

Rules:
- Answer the student's question directly and briefly.
- Stay on the class topic. Do not invent unrelated facts.
- If the question is inappropriate, off-topic, or nonsense, politely say you can't help with that and redirect to the class topic.
- Never make up definitions.
- {_lang_rule(lang)}
- Keep it under 200 characters."""

    # 直前の生徒発言だけを見る（黒板は参考程度）
    last_user = ""
    for m in reversed(history):
        if m["sender_type"] == "user":
            last_user = m["content"]
            break

    user = f"""Blackboard (context only):
{blackboard[:400] if blackboard else '(empty)'}

Student said: {last_user}

Reply to the student. Stay on topic."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def ai_stage_help(subject, title, blackboard, stage_name, history, lang="ja"):
    system = f"""You are a teacher assistant for a "{subject}" class titled "{title}".
{_lang_rule(lang)}"""
    user = f"""Blackboard content:
{blackboard or '(empty)'}

Current lesson stage: {stage_name}

Provide one sentence or a short bullet list the teacher can say or write at this stage.
Append it to the blackboard. Plain text only, keep it short."""
    msgs = [{"role": "system", "content": system}]
    msgs.extend(_history(history, limit=10))
    msgs.append({"role": "user", "content": user})
    return msgs