#!/usr/bin/env python3
"""
RSS源定期检测脚本
每周自动运行，测试可用RSS源

发现新可用源时更新到 news_monitor.py
发现源失效时记录告警
"""

import urllib.request
import urllib.error
import sys
import json
from datetime import datetime
from pathlib import Path

# 待测试的候选RSS源
CANDIDATE_SOURCES = [
    # 教育类（幼教相关）
    ("芥末堆", "https://www.ijiandao.com/feed"),
    ("多知网", "https://www.duozhi.com/rss"),
    ("黑板洞察", "https://www.heibandongcha.com/rss"),
    ("教培内参", "https://www.jiaopeineican.com/rss"),
    
    # 科技/AI类
    ("机器之心", "https://www.jiqizhixin.com/rss"),
    ("虎嗅", "https://www.huxiu.com/rss/0.xml"),
    ("36kr", "https://feed.36kr.com/"),
    ("钛媒体", "https://www.tmtpost.com/rss"),
    ("量子位", "https://www.qbitai.com/feed"),
    ("新智元", "https://syncedreview.com/feed/"),
    
    # 创业/商业类
    ("小马谋士", "https://www.xiaomazhi.com/feed"),
    ("生财有术", "https://readmore.fun/feed"),
    ("投资界", "https://www.pedaily.cn/rss/"),
    ("福布斯中国", "https://www.forbeschina.com/rss/"),
    ("财富中文网", "http://www.fortunechina.com/rss/feed"),
    
    # 新闻综合
    ("央视新闻", "http://www.cctv.com/rss/news.xml"),
    ("新华网", "http://www.xinhuanet.com/rss/news.xml"),
    ("BBC中文", "https://feeds.bbci.co.uk/zhongwen/simplified/rss.xml"),
    
    # 央视子频道
    ("央视财经", "http://www.cctv.com/finance/rss.xml"),
    ("央视国际", "http://www.cctv.com/news/rss/index.xml#world"),
]

# 当前在用的源（用于对比）
CURRENT_SOURCES = {
    "InfoQ": "https://feed.infoq.com/",
    "OSCHINA": "https://www.oschina.net/news/rss",
    "Solidot": "https://www.solidot.org/index.rss",
    "少数派": "https://sspai.com/feed",
    "创业邦": "https://www.cyzone.cn/rss/",
    "经济观察报": "https://www.eeo.com.cn/rss.xml",
}


def test_source(name: str, url: str) -> dict:
    """测试单个RSS源"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            # 尝试多种编码
            for enc in ['utf-8', 'gbk', 'gb2312']:
                try:
                    content = raw.decode(enc)
                    if "<item>" in content or "<entry>" in content or "<feed" in content.lower():
                        return {"status": "✅", "name": name, "url": url, "info": "有效RSS"}
                    # 不是这个编码，尝试下一个
                except:
                    continue
            # 所有编码都试过但没找到RSS标记
            return {"status": "⚠️", "name": name, "url": url, "info": "非RSS格式"}
    except urllib.error.HTTPError as e:
        return {"status": "❌", "name": name, "url": url, "info": f"HTTP {e.code}"}
    except urllib.error.URLError:
        return {"status": "❌", "name": name, "url": url, "info": "网络不通"}
    except Exception as e:
        return {"status": "❌", "name": name, "url": url, "info": str(type(e).__name__)}
    
    return {"status": "❌", "name": name, "url": url, "info": "未知错误"}


def main():
    print(f"RSS源检测 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
    results_dir = base_dir / "news" / "source_check"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # 测试候选源
    print("\n[候选源检测]")
    new_working = []
    
    for name, url in CANDIDATE_SOURCES:
        result = test_source(name, url)
        status_icon = result["status"]
        print(f"{status_icon} {name}: {result['info']}")
        
        if result["status"] == "✅":
            new_working.append(result)
    
    # 测试当前源是否正常
    print("\n[当前源健康检查]")
    current_issues = []
    
    for name, url in CURRENT_SOURCES.items():
        result = test_source(name, url)
        status_icon = result["status"]
        print(f"{status_icon} {name}: {result['info']}")
        
        if result["status"] != "✅":
            current_issues.append(result)
    
    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(),
        "new_working": new_working,
        "current_issues": current_issues
    }
    
    report_file = results_dir / f"check_{timestamp}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 汇总
    print("\n" + "=" * 60)
    print("汇总:")
    print(f"  新发现可用源: {len(new_working)} 个")
    for r in new_working:
        print(f"    - {r['name']}: {r['url']}")
    
    print(f"  当前源异常: {len(current_issues)} 个")
    for r in current_issues:
        print(f"    - {r['name']}: {r['info']}")
    
    if new_working:
        print("\n💡 建议更新 news_monitor.py 的 DEFAULT_SOURCES")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
