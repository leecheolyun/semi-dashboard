# 반도체 · 기판 대시보드

국내외 반도체/기판 주요 기업의 시세(Yahoo Finance)와 기업별·업계 뉴스(Google 뉴스 RSS)를 한 페이지에서 보는 정적 사이트.

- 기업 목록: `companies.json` (segment, region KR/GLOBAL, ticker, news_query, `news_exclude` 제목 필터, `news_exclude_sources` 매체 필터)
- 채용정보: `companies.json` 의 `careers_url`(모든 기업) + `jobs` 소스 설정(workday / eightfold / amd / asml_sitemap / samsung_kr / lg_careers / sk_careers, 구현은 `scripts/jobs_sources.py`). 피드가 없는 기업은 공식 채용 페이지 링크만 표시
- 업계 뉴스 토픽: `topics.json` (토픽별 한국어/영어 검색어, `per_topic`, `window`)
- 데이터 갱신: `pip install -r requirements.txt && python scripts/fetch.py` → `data/data.json`
- 로컬 보기: `python -m http.server 8765` → http://127.0.0.1:8765/
- URL: `?view=news&topic=hbm&region=KR`, `?view=jobs&co=micron`, `?seg=substrate&q=FC-BGA`

## 배포 (GitHub Pages)
1. 저장소에 push
2. Settings → Pages → Source: **GitHub Actions**
3. `.github/workflows/update.yml` 이 3시간마다(및 main push, 수동 실행 시) 데이터를 갱신·커밋하고 Pages 로 배포
