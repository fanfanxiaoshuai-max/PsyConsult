import asyncio

import pytest

from app.infra.cache import SemanticCache


def test_newly_written_exact_answer_is_visible_immediately():
    class Client:
        def query(self, **kwargs):
            # A bounded read can omit a just-inserted entity.
            if kwargs.get('consistency_level') != 'Strong':
                return []
            return [{'question': 'same question', 'answer': 'cached answer', 'scope': 'user', 'user_id': 'doctor_test'}]

    cache = SemanticCache()
    cache._available = True
    cache._client = Client()
    hit = asyncio.run(cache.get_cache('same question', 'doctor_test'))
    assert hit['answer'] == 'cached answer'
    assert hit['level'] == 'L1_EXACT'


@pytest.mark.parametrize('similarity,expected_hit', [(1.0, True), (0.97, True), (0.89, False), (-0.5, False)])
def test_semantic_cache_uses_cosine_similarity_direction(similarity, expected_hit):
    class Client:
        def query(self, **kwargs):
            return []

        def search(self, **kwargs):
            assert kwargs.get('consistency_level') == 'Strong'
            return [[{'distance': similarity, 'entity': {'question': 'related question', 'answer': 'answer'}}]]

    class Embeddings:
        async def aembed_query(self, text):
            return [1.0, 0.0]

    cache = SemanticCache()
    cache._available = True
    cache._client = Client()
    cache._embeddings = Embeddings()
    hit = asyncio.run(cache.get_cache('a related question', 'doctor_test'))
    assert (hit is not None) is expected_hit
    if expected_hit:
        assert hit['distance'] == pytest.approx(1 - similarity)
