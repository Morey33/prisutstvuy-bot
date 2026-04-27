import os
import json
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CLASSIFY_SYSTEM = """Ты — классификатор состояния человека. 
Человек пишет тебе свободным текстом о том, как себя чувствует.
Твоя задача: определить состояние и вернуть ТОЛЬКО JSON без пояснений.

Категории состояний:
- anxiety   — тревога, беспокойство, страх, нервозность, паника, стресс
- fatigue   — усталость, апатия, нет сил, опустошённость, вялость
- thoughts  — много мыслей, голова не останавливается, думаю слишком много
- scrolling — залипание в телефоне, соцсети, прокрастинация через контент
- unfocus   — расфокус, не могу начать, откладываю, нет концентрации
- evening   — вечер, итоги дня, рефлексия, перед сном
- morning   — утро, начало дня, просыпаюсь, планы

Если не уверен — выбирай anxiety как дефолт.

Верни строго этот JSON:
{"state": "<категория>", "word": "<одно слово — ключевая эмоция на русском>"}

Примеры:
Вход: "что-то тревожно как-то, мысли скачут"
Выход: {"state": "anxiety", "word": "тревога"}

Вход: "устал, ничего не хочется"
Выход: {"state": "fatigue", "word": "пустота"}

Вход: "залип в ленте уже час"
Выход: {"state": "scrolling", "word": "залипание"}
"""

async def classify_state(text: str) -> tuple[str, str]:
    """Возвращает (state, word) — категорию и ключевое слово."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": text}
            ],
            max_tokens=60,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        state = data.get("state", "anxiety")
        word = data.get("word", "состояние")
        return state, word
    except Exception:
        return "anxiety", "состояние"


DIALOGUE_SYSTEM = """Ты — Здесь. Тихий проводник по вниманию.

Ты не коуч, не терапевт, не гуру. Ты — спокойный, тёплый голос, который помогает человеку 
заметить, где прямо сейчас его внимание, и мягко вернуть его туда, где важно быть.

Принципы:
— Сначала признай состояние. Не исправляй, не советуй немедленно.
— Говори коротко. Максимум 3-4 предложения.
— Живой, простой язык. Никогда: «осознанность», «трансформация», «энергия», «вибрации».
— Не обещай результат. Не говори «станет лучше» или «ты справишься».
— Не диагностируй.
— Если человек описывает тяжёлое состояние — мягко скажи что не можешь помочь с этим, 
  предложи обратиться к близкому или специалисту.
— Завершай практику открытым вопросом или тишиной. Не требуй отчёта.
— Никогда не хвали за то, что человек «практикует».
"""

async def free_dialogue(history: list[dict]) -> str:
    """Свободный диалог для платных пользователей."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": DIALOGUE_SYSTEM}] + history,
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Что-то пошло не так. Попробуй ещё раз или просто напиши мне что чувствуешь."
