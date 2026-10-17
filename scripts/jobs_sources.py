"""채용공고 수집기 (공개 · 무료 · 로그인 불필요 소스만).

지원 타입 (companies.json 의 각 회사 "jobs": [ {...}, ... ])
  workday        {"type":"workday","host":"micron.wd1.myworkdayjobs.com","tenant":"micron","site":"External","search":""}
                 각 사 공개 채용 사이트가 쓰는 /wday/cxs/<tenant>/<site>/jobs JSON
  eightfold      {"type":"eightfold","base":"https://careers.qualcomm.com","domain":"qualcomm.com"}
                 Eightfold 공개 검색 API (/api/pcsx/search, robots.txt 허용 경로)
  amd            {"type":"amd"}  careers.amd.com/api/jobs (robots crawl-delay 5 준수)
  asml_sitemap   {"type":"asml_sitemap"}  asml.com 공식 채용공고 sitemap (제목은 URL 에서 복원)
  samsung_kr     {"type":"samsung_kr","company":"삼성전기"}  samsungcareers.com 공개 공고 목록
  lg_careers     {"type":"lg_careers","company_code":"LGIT"}  careers.lg.com 공개 공고 목록
  sk_careers     {"type":"sk_careers","corp":"SK hynix"}  skcareers.com 공개 공고 목록

각 함수는 dict 리스트를 반환: title, location, posted(YYYY-MM-DD|None), posted_approx, deadline, link, source
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def _today():
    return datetime.now(timezone.utc).date()


def _job(title, link, source, location="", posted=None, approx=False, deadline=None, extra=None):
    d = {"title": (title or "").strip(), "location": (location or "").strip(), "posted": posted,
         "posted_approx": approx, "deadline": deadline, "link": link, "source": source}
    if extra:
        d.update(extra)
    return d


# ------------------------------------------------------------------ Workday
_WD_REL = re.compile(r"(\d+)\+?\s+Days?\s+Ago", re.I)


def _wd_posted(txt: str):
    if not txt:
        return None, True
    t = txt.lower()
    if "today" in t:
        return _today().isoformat(), False
    if "yesterday" in t:
        return (_today() - timedelta(days=1)).isoformat(), False
    m = _WD_REL.search(txt)
    if m:
        n = int(m.group(1))
        return (_today() - timedelta(days=n)).isoformat(), "+" in txt
    return None, True


def workday(get_json, cfg, limit):
    host, tenant, site = cfg["host"], cfg["tenant"], cfg["site"]
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out = []
    for offset in (0, 20):
        j = get_json(url, method="POST", json={"appliedFacets": {}, "limit": 20, "offset": offset,
                                               "searchText": cfg.get("search", "")},
                     headers={"Accept-Language": "en-US"})  # postedOn 문구를 영어로 받아 날짜 계산
        posts = j.get("jobPostings") or []
        for p in posts:
            posted, approx = _wd_posted(p.get("postedOn", ""))
            out.append(_job(p.get("title"), f"https://{host}/{site}{p.get('externalPath', '')}", "Workday",
                            p.get("locationsText", ""), posted, approx))
        if len(posts) < 20:
            break
    return out


# ------------------------------------------------------------------ Eightfold
def eightfold(get_json, cfg, limit):
    base, domain = cfg["base"].rstrip("/"), cfg["domain"]
    out = []
    for start in range(0, max(limit, 10), 10):
        j = get_json(f"{base}/api/pcsx/search", params={"domain": domain, "query": "", "location": "",
                                                          "start": start, "sort_by": "timestamp"})
        pos = (j.get("data") or {}).get("positions") or []
        for p in pos:
            ts = p.get("postedTs")
            posted = datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None
            locs = p.get("standardizedLocations") or p.get("locations") or []
            loc = locs[0] + (f" 외 {len(locs) - 1}곳" if len(locs) > 1 else "") if locs else ""
            out.append(_job(p.get("name"), base + p.get("positionUrl", ""), "Eightfold", loc, posted))
        if len(pos) < 10:
            break
    return out


# ------------------------------------------------------------------ AMD (careers.amd.com)
def amd(get_json, cfg, limit):
    out = []
    for page in (1, 2):
        if page > 1:
            time.sleep(5)  # robots.txt crawl-delay: 5
        j = get_json("https://careers.amd.com/api/jobs",
                     params={"page": page, "sortBy": "posted_date", "descending": "true", "internal": "false"})
        for it in j.get("jobs", []):
            d = it.get("data", {})
            posted = (d.get("posted_date") or "")[:10] or None
            out.append(_job(d.get("title"), f"https://careers.amd.com/careers-home/jobs/{d.get('slug')}",
                            "careers.amd.com", d.get("full_location") or d.get("location_name"), posted))
    return out


# ------------------------------------------------------------------ ASML (공식 sitemap)
_ASML_ID = re.compile(r"-?j(\d{8})$")


def _asml_title(slug: str) -> str:
    slug = _ASML_ID.sub("", slug).strip("-")
    words = [w for w in re.split(r"-+", slug) if w]
    small = {"and", "or", "of", "in", "for", "the", "to", "a", "at", "with"}
    keep_upper = {"euv", "duv", "hr", "it", "ai", "ic", "pcb", "us", "usa", "ehs", "r&d", "rd", "sw", "hw", "qa", "plm", "sap", "cs", "hmi", "nxe", "exe"}
    res = []
    for i, w in enumerate(words):
        lw = w.lower()
        res.append(w.upper() if lw in keep_upper else (lw if (i and lw in small) else lw.capitalize()))
    return " ".join(res)


def asml_sitemap(get_text, cfg, limit):
    xml_text = get_text("https://www.asml.com/en/job_posting-sitemap.xml")
    root = ET.fromstring(xml_text.strip().encode())
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    out = []
    for u in root.findall("s:url", ns):
        loc = (u.findtext("s:loc", default="", namespaces=ns) or "").strip()
        lastmod = (u.findtext("s:lastmod", default="", namespaces=ns) or "").strip()[:10] or None
        slug = loc.rstrip("/").rsplit("/", 1)[-1]
        out.append(_job(_asml_title(slug), loc, "asml.com sitemap", "", lastmod, True,
                        extra={"title_from_url": True}))
    return out


# ------------------------------------------------------------------ 삼성 (samsungcareers.com)
_SS_LI = re.compile(r'<a href="/#none"\s+data-value="([\d,]+)">\s*<p class="company">(.*?)</p>\s*'
                    r'<h3 class="title">(.*?)</h3>.*?<span class="period">\s*(.*?)\s*</span>', re.S)


def samsung_kr(post_text, cfg, limit):
    out, page, maxp = [], 1, 1
    while page <= maxp and page <= 5:
        h = post_text("https://www.samsungcareers.com/hr/list.data",
                      data={"currentPageNo": page, "intNo": 0, "strVal": "", "strTxt": "", "strKey": "",
                            "strOrderBy": "", "strEntity": ""},
                      headers={"Referer": "https://www.samsungcareers.com/hr/"})
        m = re.search(r'data-max="(\d+)"', h)
        maxp = int(m.group(1)) if m else 1
        for seq, comp, title, period in _SS_LI.findall(h):
            comp = html.unescape(re.sub(r"\s+", " ", comp)).strip()
            if cfg.get("company") and cfg["company"] not in comp:
                continue
            dates = re.findall(r"\d{4}\.\d{2}\.\d{2}", period)
            posted = dates[0].replace(".", "-") if dates else None
            deadline = dates[1].replace(".", "-") if len(dates) > 1 else None
            out.append(_job(html.unescape(re.sub(r"\s+", " ", title)), f"https://www.samsungcareers.com/hr/?no={seq.replace(',', '')}",
                            "samsungcareers.com", comp, posted, False, deadline))
        page += 1
    return out


# ------------------------------------------------------------------ LG (careers.lg.com)
def lg_careers(get_json, cfg, limit):
    body = {"lnbSearch": "", "hashTagText": "", "recDate": "POST_START_DATE", "order": "DESC",
            "careerList": [], "companyCodeList": [cfg["company_code"]], "jobGroupList": [], "desireLocList": []}
    j = get_json("https://api.careers.lg.com/rmk/job/retrieveJobNoticesList", method="POST", json=body,
                 headers={"Origin": "https://careers.lg.com", "Referer": "https://careers.lg.com/"})
    out = []
    for n in (j.get("data") or {}).get("jobNoticeList") or []:
        dl = (n.get("recEndDateTime") or "")[:10].replace(".", "-") or None
        typ = " · ".join(x for x in (n.get("careerTypeName"), n.get("jobGroupName")) if x)
        out.append(_job(n.get("jobNoticeName"), f"https://careers.lg.com/apply/detail?id={n.get('jobNoticeId')}",
                        "careers.lg.com", n.get("workLocationName", ""), None, False, dl, {"kind": typ}))
    return out


# ------------------------------------------------------------------ SK (skcareers.com)
def _sk_date(s):
    m = re.match(r"([A-Za-z]+ \d{1,2}, \d{4})", s or "")
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{4})\s*[.\-년]\s*(\d{1,2})\s*[.\-월]\s*(\d{1,2})", s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def sk_careers(post_json, cfg, limit):
    j = post_json("https://www.skcareers.com/Recruit/GetRecruitList",
                  data={"sort": "2", "searchText": "", "corpCode": "", "jobRole": "0", "recruitType": "",
                        "workingType": "", "workingRegion": ""},
                  headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.skcareers.com/Recruit"})
    out = []
    for d in j.get("list", []):
        corps = cfg.get("corp") or []
        corps = [corps] if isinstance(corps, str) else corps
        if corps and d.get("corpName", "").lower() not in {c.lower() for c in corps}:
            continue
        out.append(_job(html.unescape(d.get("title", "")), f"https://www.skcareers.com/Recruit/Detail/{d.get('noticeID')}",
                        "skcareers.com", d.get("workingArea", ""), _sk_date(d.get("start")), False,
                        _sk_date(d.get("end")), {"kind": d.get("jobRole", "")}))
    return out
