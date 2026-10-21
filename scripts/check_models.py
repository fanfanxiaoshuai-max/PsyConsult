"""Explicit paid API smoke test. Run only after configuring your own key."""
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    values = dotenv_values(ROOT / 'agent' / '.env')
    key = values.get('DASHSCOPE_API_KEY', '')
    if not key or not key.strip() or key.startswith(('replace', 'offline-test')):
        raise SystemExit('Set your actual DASHSCOPE_API_KEY in agent/.env first.')
    load_dotenv(ROOT / 'agent' / '.env')
    sys.path.insert(0, str(ROOT / 'agent'))
    from config import get_settings
    from langchain_openai import ChatOpenAI
    from langchain_community.embeddings import DashScopeEmbeddings

    settings = get_settings()
    try:
        response = ChatOpenAI(**settings.get_model_config(), temperature=0, timeout=45,
                              max_retries=0).invoke('只回复 OK')
        if not response.content:
            raise ValueError('empty chat response')
        print('PASS: chat model returned content')
        vector = DashScopeEmbeddings(model='text-embedding-v2',
                                     dashscope_api_key=settings.get_embedding_api_key()).embed_query('复现验证')
        if len(vector) != 1536:
            raise ValueError('embedding dimension must match existing collections: 1536')
        print('PASS: embedding returned 1536 dimensions')
    except Exception as exc:
        # Do not print credentials or provider exception payloads.
        raise SystemExit(f'Model check failed ({type(exc).__name__}). Check region, access and quota.') from None


if __name__ == '__main__':
    main()
