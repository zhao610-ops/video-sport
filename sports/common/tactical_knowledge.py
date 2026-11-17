"""本地中文战术卡片检索，不联网、不加载额外模型。"""

import copy
import json
import re
from pathlib import Path


DEFAULT_KNOWLEDGE = Path(__file__).resolve().parents[2] / 'knowledge' / 'football_tactics.json'


def normalize(text):
    return re.sub(r'[\s\-]+', '', text.casefold())


def bigrams(text):
    return {text[index:index+2] for index in range(len(text)-1)}


class TacticalKnowledgeBase:
    def __init__(self, path=DEFAULT_KNOWLEDGE):
        with open(path, encoding='utf-8') as stream:
            self.data = json.load(stream)
        if self.data.get('schema_version') != 'football-knowledge-1.0':
            raise ValueError('知识库版本格式无效')
        self.sources = {source['id']: source for source in self.data['sources']}
        cards = self.data['cards']
        if not cards or len({card['id'] for card in cards}) != len(cards):
            raise ValueError('知识卡片为空或编号重复')
        for card in cards:
            if not re.fullmatch(r'K\d{3}', card['id']) or not card['source_ids']:
                raise ValueError('知识卡片编号或来源无效')
            if any(source not in self.sources for source in card['source_ids']):
                raise ValueError('知识卡片引用了不存在的来源')
        self.cards = cards

    def search(self, query, limit=3):
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise ValueError('知识检索词应为1到500个字符')
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError('知识检索条数应为1到5')
        query_text = normalize(query)
        query_pairs = bigrams(query_text)
        ranked = []
        for card in self.cards:
            terms = [normalize(term) for term in [card['title'], *card['aliases']]]
            # 明确术语优先；仅在题名和同义词上做双字片段匹配，避免全文噪声。
            exact = max((len(term) for term in terms if term in query_text), default=0)
            pairs = set().union(*(bigrams(term) for term in terms))
            overlap = len(pairs & query_pairs)
            if not exact and (overlap < 2 or overlap / max(1, len(query_pairs)) < .2):
                continue
            ranked.append((exact*10 + overlap, card))
        ranked.sort(key=lambda item: (-item[0], item[1]['id']))
        matches = []
        for score, card in ranked[:limit]:
            item = copy.deepcopy(card)
            item['sources'] = [copy.deepcopy(self.sources[source]) for source in item.pop('source_ids')]
            item['retrieval_score'] = score
            matches.append(item)
        return {'knowledge_version': self.data['version'], 'query': query, 'matches': matches,
                'status': 'matched' if matches else 'no_match',
                'notice': '中文摘要与项目适用说明；检索分数不是置信度。知识不是当前比赛事实；无匹配不代表该概念不存在。'}
