# 반도체 · 기판 대시보드

국내외 반도체/기판 주요 기업의 시세(Yahoo Finance)와 기업별·업계 뉴스(Google 뉴스 RSS)를 한 페이지에서 보는 정적 사이트.

- 기업 목록: `companies.json` (segment, region KR/GLOBAL, ticker, news_query, `news_exclude` 제목 필터, `news_exclude_sources` 매체 필터)
- 업계 뉴스 토픽: `topics.json` (토픽별 한국어/영어 검색어, `per_topic`, `window`)
- 데이터 갱신: `pip install -r requirements.txt && python scripts/fetch.py` → `data/data.json`
- 로컬 보기: `python -m http.server 8765` → http://127.0.0.1:8765/
- URL: `?view=news&topic=hbm&region=KR`, `?seg=substrate&q=FC-BGA`

## 배포 (GitHub Pages)
1. 저장소에 push
2. Settings → Pages → Source: **GitHub Actions**
3. `.github/workflows/update.yml` 이 3시간마다(및 main push, 수동 실행 시) 데이터를 갱신·커밋하고 Pages 로 배포
