#!/usr/bin/env python3
"""
新闻监控器 (News Monitor)
幼教 + AI科技 + 赚钱项目 资讯流

完整闭环:
- 抓取: RSS/搜索/API 多源获取
- 过滤: 去重 + 关键词过滤 + 日期过滤
- 整理: 格式化 + 摘要生成
- 推送: 飞书卡片推送
- 记录: 已推送ID存储，避免重复
- 反馈: 用户可标记感兴趣/不感兴趣

存储结构:
news/
├── cache/              # 已缓存的新闻(去重用)
├── read_history.json   # 已读历史
├── sources.json        # 订阅源配置
└── pushing_today.json  # 今日已推送记录

推送频率:
- 早9点: 今日要闻 (各3条)
- 晚8点: 晚间资讯汇总

关注领域:
1. 幼少儿教育培训
2. AI & 科技圈
3. 赚钱项目/创业
"""

import json
import re
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import xml.etree.ElementTree as ET


# 搜索API配置
BING_API_KEY = ""  # 可选填
USE_BING = bool(BING_API_KEY)

# 默认订阅源（实测可用）
DEFAULT_SOURCES = {
    "幼教": [
        {"name": "黑板洞察", "url": "https://www.heibandongcha.com/rss", "type": "rss"},
    ],
    "AI科技": [
        {"name": "InfoQ", "url": "https://feed.infoq.com/", "type": "rss"},
        {"name": "OSCHINA", "url": "https://www.oschina.net/news/rss", "type": "rss"},
        {"name": "Solidot", "url": "https://www.solidot.org/index.rss", "type": "rss"},
        {"name": "钛媒体", "url": "https://www.tmtpost.com/rss", "type": "rss"},
        {"name": "量子位", "url": "https://www.qbitai.com/feed", "type": "rss"},
        {"name": "新智元", "url": "https://syncedreview.com/feed/", "type": "rss"},
    ],
    "赚钱": [
        {"name": "创业邦", "url": "https://www.cyzone.cn/rss/", "type": "rss"},
        {"name": "经济观察报", "url": "https://www.eeo.com.cn/rss.xml", "type": "rss"},
        {"name": "少数派", "url": "https://sspai.com/feed", "type": "rss"},
    ]
}

# 关键词配置
KEYWORDS = {
    "幼教": ["教育", "培训", "幼儿", "少儿", "K12", "STEAM", "素质教育", "早教", "托育", "幼儿园", "教培", "营地", "游学"],
    "AI科技": ["AI", "人工智能", "大模型", "GPT", "LLM", "ChatGPT", "Grok", "Claude", "Gemini", "科技", "创业", "融资", "技术", "软件", "开发者", "开源"],
    "赚钱": ["赚钱", "变现", "副业", "创业", "项目", "月入", "年收入", "商业模式", "盈利", "ROI", "GMV", "投资", "融资", "上市", "并购"]
}


@dataclass
class NewsItem:
    """新闻条目"""
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: str
    published_at: str
    push_status: str  # pending/sent/interested/skipped


class NewsMonitor:
    """新闻监控器"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        self.base_dir = Path(base_dir)
        self.news_dir = self.base_dir / "news"
        self.cache_dir = self.news_dir / "cache"
        self.read_history_file = self.news_dir / "read_history.json"
        self.pushed_today_file = self.news_dir / "pushing_today.json"

        # 创建目录
        for d in [self.news_dir, self.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 初始化文件
        if not self.read_history_file.exists():
            self._save_json(self.read_history_file, {"read": [], "interested": [], "skipped": []})

        if not self.pushed_today_file.exists():
            self._save_json(self.pushed_today_file, {"date": "", "items": []})

    # ========== 核心功能 ==========

    def fetch_all(self) -> Dict[str, List[NewsItem]]:
        """抓取所有分类的新闻"""
        results = {}

        for category, sources in DEFAULT_SOURCES.items():
            results[category] = self.fetch_category(category, sources)

        return results

    def fetch_category(self, category: str, sources: List[Dict] = None) -> List[NewsItem]:
        """抓取指定分类的新闻"""
        if sources is None:
            sources = DEFAULT_SOURCES.get(category, [])

        all_items = []
        keywords = KEYWORDS.get(category, [])

        for source in sources:
            try:
                if source["type"] == "rss":
                    items = self._fetch_rss(source, category, keywords)
                    all_items.extend(items)
            except Exception as e:
                print(f"抓取失败 {source['name']}: {e}")
                continue

        # 去重
        all_items = self._deduplicate(all_items)

        # 按时间排序
        all_items.sort(key=lambda x: x.published_at, reverse=True)

        return all_items[:20]  # 最多20条

    def search_news(self, query: str, category: str = None, limit: int = 10) -> List[NewsItem]:
        """
        搜索新闻（使用Bing搜索）
        """
        if not query:
            return []

        items = []

        try:
            # 使用Bing搜索
            if USE_BING and BING_API_KEY:
                items = self._bing_search(query, limit)
            else:
                # 使用百度搜索（免费但有限制）
                items = self._baidu_search(query, limit)

            # 过滤关键词
            if category:
                keywords = KEYWORDS.get(category, [])
                items = [i for i in items if any(kw in i.title or kw in i.summary for kw in keywords)]

        except Exception as e:
            print(f"搜索失败: {e}")

        return items[:limit]

    def _bing_search(self, query: str, limit: int) -> List[NewsItem]:
        """Bing搜索"""
        # 实现Bing搜索API调用
        url = f"https://api.bing.microsoft.com/v7.0/news/search?q={query}&count={limit}"

        req = urllib.request.Request(url, headers={
            "Ocp-Apim-Subscription-Key": BING_API_KEY
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        items = []
        for item in data.get("value", []):
            news = NewsItem(
                id=self._generate_id(item["url"]),
                title=item.get("name", ""),
                summary=item.get("description", "")[:200],
                url=item.get("url", ""),
                source=item.get("provider", [{}])[0].get("name", "Bing"),
                category="",
                published_at=item.get("datePublished", "")[:10],
                push_status="pending"
            )
            items.append(news)

        return items

    def _baidu_search(self, query: str, limit: int) -> List[NewsItem]:
        """简单的百度搜索（网页抓取）"""
        # 注意：百度搜索有反爬，这里只是演示结构
        # 实际使用时建议使用Bing API或专业的新闻API

        url = f"https://www.baidu.com/s?wd={query}&rn={limit}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })

            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8")

            # 简单的正则提取（实际生产环境建议用BeautifulSoup）
            items = self._parse_baidu_results(html, query)

            return items

        except Exception as e:
            print(f"百度搜索失败: {e}")
            return []

    def _parse_baidu_results(self, html: str, query: str) -> List[NewsItem]:
        """解析百度搜索结果"""
        items = []

        # 匹配标题和链接
        pattern = r'<h3 class="news-title.*?<a href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html, re.DOTALL)

        for url, title in matches[:10]:
            title = re.sub(r'<[^>]+>', '', title)
            news = NewsItem(
                id=self._generate_id(url),
                title=title.strip(),
                summary="",
                url=url,
                source="百度",
                category="",
                published_at=datetime.now().date().isoformat(),
                push_status="pending"
            )
            items.append(news)

        return items

    def _fetch_rss(self, source: Dict, category: str, keywords: List[str]) -> List[NewsItem]:
        """抓取RSS源（使用标准库xml.etree）"""
        items = []

        try:
            url = source["url"]
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })

            with urllib.request.urlopen(req, timeout=15) as response:
                raw_content = response.read()
                # 检测编码
                encoding = response.headers.get_content_charset() or 'utf-8'
                try:
                    xml_text = raw_content.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    # 尝试gbk或gb2312
                    try:
                        xml_text = raw_content.decode('gbk')
                    except:
                        xml_text = raw_content.decode('utf-8', errors='ignore')

            # 解析XML
            root = ET.fromstring(xml_text)

            # RSS格式
            channel = root.find("channel")
            if channel is not None:
                entries = channel.findall("item")
            else:
                # Atom格式
                entries = root.findall(".//entry")

            for entry in entries[:15]:  # 最多15条
                # 获取标题
                title_elem = entry.find("title")
                title = title_elem.text if title_elem is not None else ""
                if title_elem is not None and title_elem.text:
                    title = title_elem.text
                else:
                    title = ""

                # 获取链接
                link_elem = entry.find("link")
                link = ""
                if link_elem is not None:
                    if link_elem.text:
                        link = link_elem.text
                    else:
                        link = link_elem.get("href", "")

                # 获取摘要
                summary = ""
                for tag in ["description", "summary", "content"]:
                    elem = entry.find(tag)
                    if elem is not None and elem.text:
                        summary = self._clean_html(elem.text)
                        break

                # 获取发布日期
                published = datetime.now().date().isoformat()
                for tag in ["pubDate", "published", "updated"]:
                    elem = entry.find(tag)
                    if elem is not None and elem.text:
                        published = self._parse_date(elem.text)
                        break

                # 关键词过滤
                if keywords and not any(kw in (title or "") or kw in (summary or "") for kw in keywords):
                    continue

                news = NewsItem(
                    id=self._generate_id(link or title),
                    title=title or "无标题",
                    summary=summary[:200] if summary else "",
                    url=link,
                    source=source["name"],
                    category=category,
                    published_at=published,
                    push_status="pending"
                )
                items.append(news)

        except Exception as e:
            print(f"RSS抓取失败 {source['url']}: {e}")

        return items

    # ========== 推送功能 ==========

    def push_to_feishu(self, news_items: Dict[str, List[NewsItem]], force: bool = False) -> bool:
        """
        推送新闻到飞书
        """
        if not news_items:
            return False

        # 检查是否今日已推送
        today = datetime.now().date().isoformat()
        pushed_today = self._load_json(self.pushed_today_file)

        if not force and pushed_today.get("date") == today and pushed_today.get("items"):
            print(f"今日已推送过，跳过")
            return False

        try:
            from feishu_alert import FeishuAlert
            feishu = FeishuAlert(self.base_dir)

            # 构建卡片内容
            content = self._build_news_card(news_items)

            # 发送
            result = feishu._send_message(content)

            if result:
                # 记录已推送
                pushed_ids = []
                for category, items in news_items.items():
                    for item in items:
                        pushed_ids.append(item.id)

                self._save_json(self.pushed_today_file, {
                    "date": today,
                    "items": pushed_ids
                })

                return True

        except Exception as e:
            print(f"推送失败: {e}")

        return False

    def _build_news_card(self, news_items: Dict[str, List[NewsItem]]) -> dict:
        """构建飞书新闻卡片"""
        elements = []

        # 标题
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"📰 **今日资讯速览** | {datetime.now().strftime('%Y-%m-%d')}"
            }
        })

        # 分类遍历
        category_names = {
            "幼教": "👶 幼教行业",
            "AI科技": "🤖 AI & 科技",
            "赚钱": "💰 赚钱项目"
        }

        for category, items in news_items.items():
            if not items:
                continue

            elements.append({"tag": "hr"})

            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{category_names.get(category, category)}**"
                }
            })

            # 最多显示5条
            for item in items[:5]:
                title = item.title[:30] + "..." if len(item.title) > 30 else item.title
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"• [{title}]({item.url})\n  _{item.source} · {item.published_at}_"
                    }
                })

        # 底部
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "fields": [
                {"tag": "plain_text", "content": f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
            ]
        })

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "📬 每日资讯"},
                    "template": "blue"
                },
                "elements": elements
            }
        }

    # ========== 用户反馈 ==========

    def mark_interested(self, news_id: str) -> bool:
        """标记感兴趣"""
        history = self._load_json(self.read_history_file)

        if news_id not in history.get("interested", []):
            history.setdefault("interested", []).append(news_id)

        self._save_json(self.read_history_file, history)
        return True

    def mark_skipped(self, news_id: str) -> bool:
        """标记不感兴趣"""
        history = self._load_json(self.read_history_file)

        if news_id not in history.get("skipped", []):
            history.setdefault("skipped", []).append(news_id)

        self._save_json(self.read_history_file, history)
        return True

    # ========== 工具方法 ==========

    def _generate_id(self, content: str) -> str:
        """生成唯一ID"""
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _parse_date(self, date_str: str) -> str:
        """解析日期"""
        try:
            # 尝试多种格式
            for fmt in ["%Y-%m-%d", "%a, %d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(date_str[:19], fmt).date().isoformat()
                except Exception:
                    continue

            # 默认返回今天
            return datetime.now().date().isoformat()

        except Exception:
            return datetime.now().date().isoformat()

    def _clean_html(self, html: str) -> str:
        """清理HTML标签"""
        if not html:
            return ""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', html)
        # 清理多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """去重"""
        seen_ids = set()
        unique = []

        for item in items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                unique.append(item)

        return unique

    def _load_json(self, file_path: Path) -> dict:
        """加载JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_json(self, file_path: Path, data: dict) -> None:
        """保存JSON文件"""
        temp_file = file_path.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(file_path)

    # ========== 命令行接口 ==========

    def summary(self) -> str:
        """获取新闻摘要"""
        results = self.fetch_all()

        lines = ["📰 今日资讯预览"]
        lines.append("")

        category_names = {
            "幼教": "👶 幼教",
            "AI科技": "🤖 AI科技",
            "赚钱": "💰 赚钱"
        }

        for cat, items in results.items():
            lines.append(f"【{category_names.get(cat, cat)}】({len(items)}条)")
            for item in items[:3]:
                title = item.title[:40] + "..." if len(item.title) > 40 else item.title
                lines.append(f"  • {title}")
            lines.append("")

        return "\n".join(lines)


def main():
    """命令行测试"""
    monitor = NewsMonitor()

    import sys

    if len(sys.argv) < 2:
        # 默认抓取+推送
        print("抓取新闻中...")
        results = monitor.fetch_all()
        print(f"抓取完成: 幼教{len(results.get('幼教',[]))}条, AI{len(results.get('AI科技',[]))}条, 赚钱{len(results.get('赚钱',[]))}条")
        print("\n推送测试（可跳过）...")
        # monitor.push_to_feishu(results)
        print("\n摘要预览:")
        print(monitor.summary())
        return

    cmd = sys.argv[1]

    if cmd == "fetch":
        results = monitor.fetch_all()
        print(monitor.summary())

    elif cmd == "push":
        results = monitor.fetch_all()
        if monitor.push_to_feishu(results):
            print("推送成功")
        else:
            print("推送失败或今日已推送")

    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "AI创业"
        results = monitor.search_news(query)
        print(f"搜索'{query}'结果:")
        for i, item in enumerate(results, 1):
            print(f"{i}. {item.title}")

    elif cmd == "summary":
        print(monitor.summary())

    else:
        print(f"未知命令: {cmd}")
        print("用法: python news_monitor.py [fetch|push|search|summary]")


if __name__ == "__main__":
    main()
