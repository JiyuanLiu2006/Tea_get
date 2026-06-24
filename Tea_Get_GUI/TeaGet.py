import sys
import os
import re
import csv
import json
import html
import time
import queue
import datetime
import threading
import urllib.parse
import urllib3
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

import tkinter as tk
from tkinter import messagebox, filedialog, font as tkfont
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


# Windows高分屏适配
def _setup_high_dpi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

_setup_high_dpi()

CONFIG_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# ============================================================
# 默认配置变量
# ============================================================
COLLECTOR_NAME = ""
SCHOOL_NAME = ""
COLLEGE_NAME = ""
LIST_URLS = [""]
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "采集结果.csv")
MAX_WORKERS = 15
COLLECT_DATE = datetime.date.today().strftime("%Y/%m/%d")

# 排除词汇（用于过滤非教师链接）
EXCLUDE_WORDS = [
    '首页', '上一页', '下一页', '末页', '更多', '返回', '党', '下载', '版权', '纪检',
    '介绍', '学科专业', '科学研究', '竞赛', '通知公告', '专任教师', '人才计划', '国际会议', '支部风采',
    '新闻', '概况', '师资', '招生', '就业', '科研', '合作', '邮箱', '通信工程', 'MORE',
    'ENGLISH', '双聘教授', '系统', '工作', '公告', '通知', '政策', '服务', '资源', '帮助', '党委',
    '工会', '纪委', '成果', '平台', '评估', '门户', '专栏', '活动', '关于我们', '党务',
    '旧版', '英文', 'English', '登录', '管理', '关闭', '加入收藏', '支部建设',
    '设为首页', '联系我们', '网站地图', '隐私政策', '使用条款', '关工委', '国际交流', 'Previous'
]
EXCLUDE_REGEX = re.compile('|'.join(map(re.escape, EXCLUDE_WORDS)), re.IGNORECASE)

# 单姓字典
COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔盖闫曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安"
    "常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝"
    "董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干"
    "解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮气储靳汲邴糜松井段富巫"
    "乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白"
    "怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘翟谭贡劳逄姬申扶堵冉宰郦雍璩桑桂濮牛寿通边扈燕冀"
)

# 复姓字典
COMPOUND_SURNAMES = {
    "万俟", "司马", "上官", "欧阳", "夏侯", "诸葛", "闻人", "东方", "赫连", "皇甫",
    "尉迟", "公羊", "澹台", "公冶", "宗政", "濮阳", "淳于", "单于", "太叔", "申屠",
    "公孙", "仲孙", "轩辕", "令狐", "钟离", "宇文", "长孙", "慕容", "鲜于", "闾丘"
}


def load_config_from_json():
    """从 JSON 文件加载用户配置，覆盖默认值"""
    global COLLECTOR_NAME, SCHOOL_NAME, COLLEGE_NAME, LIST_URLS
    global OUTPUT_FILE, MAX_WORKERS, COLLECT_DATE, EXCLUDE_WORDS, EXCLUDE_REGEX
    try:
        if not os.path.exists(CONFIG_JSON):
            return
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "collector_name" in cfg:
            COLLECTOR_NAME = cfg["collector_name"]
        if "school_name" in cfg:
            SCHOOL_NAME = cfg["school_name"]
        if "college_name" in cfg:
            COLLEGE_NAME = cfg["college_name"]
        if "list_urls" in cfg and isinstance(cfg["list_urls"], list):
            LIST_URLS = cfg["list_urls"]
        if "output_file" in cfg:
            OUTPUT_FILE = cfg["output_file"]
        if "max_workers" in cfg:
            MAX_WORKERS = int(cfg["max_workers"])
        if "collect_date" in cfg:
            COLLECT_DATE = cfg["collect_date"]
        if "exclude_words" in cfg and isinstance(cfg["exclude_words"], list):
            EXCLUDE_WORDS = cfg["exclude_words"]
            EXCLUDE_REGEX = re.compile('|'.join(map(re.escape, EXCLUDE_WORDS)), re.IGNORECASE)
    except Exception as e:
        print(f"[提示] 加载配置文件失败，使用默认配置：{e}")

def save_config_to_json():
    """将当前配置保存到 JSON 文件"""
    cfg = {
        "collector_name": COLLECTOR_NAME,
        "school_name": SCHOOL_NAME,
        "college_name": COLLEGE_NAME,
        "list_urls": LIST_URLS,
        "output_file": OUTPUT_FILE,
        "max_workers": MAX_WORKERS,
        "collect_date": COLLECT_DATE,
        "exclude_words": EXCLUDE_WORDS,
    }
    try:
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[警告] 保存配置失败：{e}")

# 启动时加载配置
load_config_from_json()

# ============================================================
# 日志捕获（用于 GUI 模式下重定向 print）
# ============================================================
class LogCapture:
    """将 print 输出重定向到回调函数"""
    def __init__(self, callback):
        self.callback = callback
    def write(self, text):
        if text and text.strip():
            self.callback(text.rstrip("\n\r"))
    def flush(self):
        pass

# ============================================================
# 采集核心函数
# ============================================================

def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
        if response.status_code == 200:
            return response.text
        return ""
    except Exception:
        return ""

def discover_pagination(base_url):
    """分页探测"""
    discovered_urls = {base_url}
    html_content = get_html(base_url)
    if not html_content:
        return list(discovered_urls)

    soup = BeautifulSoup(html_content, 'html.parser')
    page_patterns = [r'[\_\-]\d+\.html?', r'\d+\.htm', r'page=\d+', r'p=\d+']

    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        if any(re.search(pat, href, re.IGNORECASE) for pat in page_patterns) or \
           any(x in text for x in ['下一页', '尾页', '末页']):
            discovered_urls.add(urllib.parse.urljoin(base_url, href))

    return list(discovered_urls)

def decode_cloudflare_email(cf_string):
    """解密 Cloudflare 混淆保护的邮箱"""
    try:
        if not cf_string:
            return ""
        hex_num = int(cf_string[:2], 16)
        return ''.join(chr(int(cf_string[i:i+2], 16) ^ hex_num) for i in range(2, len(cf_string), 2))
    except Exception:
        return ""

def extract_all_emails(html_content, text_content):
    """邮箱清洗与还原"""
    if not html_content:
        return ""

    html_content = html.unescape(html_content)
    soup = BeautifulSoup(html_content, 'html.parser')
    found_emails = []

    def add_email(email_str):
        email_str = email_str.strip().strip('.').lower()
        email_str = re.sub(r'\s+', '', email_str)
        if email_str and '@' in email_str and email_str not in found_emails:
            if re.match(r'^[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10}$', email_str):
                found_emails.append(email_str)

    # 1. Cloudflare 安全节点探测与解密
    for cf_tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded = decode_cloudflare_email(cf_tag['data-cfemail'])
        if decoded:
            add_email(decoded)

    for a_cf in soup.find_all('a', href=re.compile(r'cdn-cgi/l/email-protection', re.IGNORECASE)):
        match = re.search(r'#([a-fA-F0-9]+)', a_cf.get('href', ''))
        if match:
            decoded = decode_cloudflare_email(match.group(1))
            if decoded:
                add_email(decoded)

    # 2. 标准 Mailto 协议提取
    for a in soup.find_all('a', href=re.compile(r'^mailto:', re.IGNORECASE)):
        match = re.search(
            r'mailto:\s*([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10})',
            urllib.parse.unquote(a['href']), re.IGNORECASE
        )
        if match:
            add_email(match.group(1))

    # 3. 中文混淆还原匹配
    standard_pattern = r'[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10}'
    dense_text = soup.get_text(separator='')

    replacements = {
        '[at]': '@', '(at)': '@', '（at）': '@', '【at】': '@', '_at_': '@', '（艾特）': '@',
        ' 圈 ': '@', '(圈)': '@', '（圈）': '@', '＠': '@', '#': '@', ' AT ': '@', ' a t ': '@',
        '[dot]': '.', '(dot)': '.', '（点）': '.', '【点】': '.', ' dot ': '.', '。': '.', '．': '.',
        ' D O T ': '.'
    }

    norm_text, norm_dense = text_content, dense_text
    for k, v in replacements.items():
        norm_text = norm_text.replace(k, v)
        norm_dense = norm_dense.replace(k, v)

    for ts in [norm_text, norm_dense]:
        for email in re.findall(standard_pattern, ts):
            add_email(email)

    # 4. 业务邮箱过滤
    for email in found_emails:
        email_lower = email.lower()
        if not any(x in email_lower for x in [
            'office', 'admin', 'master', 'system', 'xyw', 'nic@', 'library',
            'postmaster', 'baoming', 'advice'
        ]):
            return email
    return ""

def looks_like_name(text):
    """姓氏字典姓名校验"""
    text = text.strip()
    if not text or len(text) < 2 or len(text) > 20:
        return False

    if EXCLUDE_REGEX.search(text):
        return False

    first_part = re.sub(r'[^\u4e00-\u9fa5]', '', text.split()[0])
    if re.match(r'^[\u4e00-\u9fa5]{2,4}$', first_part):
        if first_part[0:2] in COMPOUND_SURNAMES or first_part[0] in COMMON_SURNAMES:
            return True
        return False

    if re.match(r'^[a-zA-Z\s\.]{3,20}$', text):
        return True
    return False

def extract_title(text):
    """高校职称特征序列优先匹配"""
    titles = [
        "讲席教授", "特聘教授", "长聘教授", "客座教授", "名誉教授",
        "长聘副教授", "助理教授", "副教授", "教授",
        "高级工程师", "工程师", "高级实验师", "实验师",
        "特聘研究员", "特研人员", "副研究员", "助理研究员", "研究员",
        "博士生导师", "硕士生导师", "讲师", "助教"
    ]
    text = text.replace(" ", "").replace("\n", "").replace("\r", "")
    titles.sort(key=len, reverse=True)  # 长职称优先匹配，避免子串误伤
    for title in titles:
        if title in text:
            return title
    return "教授"

def extract_teacher_links(list_url):
    """列表页解析定位"""
    html_content = get_html(list_url)
    if not html_content:
        return {}

    teacher_links = {}
    soup = BeautifulSoup(html_content, 'html.parser')

    for a in soup.find_all('a'):
        a_href = a.get('href')
        a_text = a.get_text(strip=True)
        if not a_href or not a_text:
            continue

        full_url = urllib.parse.urljoin(list_url, a_href)
        if full_url.startswith(('mailto:', 'javascript:')) or \
           full_url.lower().endswith(('.jpg', '.png', '.pdf', '.doc', '.docx', '.xlsx', '.xls')):
            continue

        candidates = [a.get('title', '').strip(), a_text] + list(a.stripped_strings)
        name_extracted = next((c for c in candidates if c and looks_like_name(c)), None)
        if name_extracted:
            # 对提取到的姓名进行噪声清洗（去除日期、数字编号等杂余信息）
            cleaned_name = clean_name_noise(name_extracted)
            # 清洗后仍是有效姓名时才使用，否则用原始提取结果
            if looks_like_name(cleaned_name) and len(cleaned_name) >= 2:
                name_extracted = cleaned_name
        if name_extracted and full_url not in teacher_links:
            teacher_links[full_url] = name_extracted

    return teacher_links

def extract_introduction(soup):
    """从教师详情页提取个人简介文本"""
    try:
        # 策略1: 尝试找到主内容容器
        intro_selectors = [
            'div.wp_articlecontent', 'div.entry', 'div.read', 'div.articlecontent',
            'div.article-content', 'div.article', 'div.content', 'div.main-content',
            'div.entry-content', 'div.wp-content', 'div.post-content', 'div.page-content',
            'div.intro', 'div.teacher-intro', 'div.teacher-info', 'div.teacher_detail',
            'div.teacher_info', 'div.profile', 'div.personal-info', 'div.info',
            'div.text', 'div.contain', 'div.main', 'div.body',
            '#content', '#article', '#main', '#page-content', '#con', '#neirong'
        ]
        for selector in intro_selectors:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator='\n', strip=True)
                if len(text) > 30:
                    return _clean_intro_text(text)

        # 策略2: 按章节标题收集所有内容段落
        section_keywords = [
            '个人简介', '教师简介', '个人介绍', '教师介绍', '基本信息',
            '个人概况', '个人经历', '工作经历', '教育经历', '教学情况',
            '研究方向', '主讲课程', '学术成果', '科研项目', '科研成果',
            '论文成果', '代表论著', '学术兼职', '社会兼职', '荣誉奖励',
            '获奖情况', '专利情况', '著作论文'
        ]

        all_sections = []
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            for elem in soup.find_all(tag):
                heading_text = elem.get_text(strip=True)
                if any(kw in heading_text for kw in section_keywords):
                    all_sections.append((elem, heading_text))

        all_sections.sort(key=lambda x: x[0].sourcepos if hasattr(x[0], 'sourcepos') else 0)

        if all_sections:
            all_parts = []
            for i, (heading_elem, heading_text) in enumerate(all_sections):
                all_parts.append(heading_text)
                for sibling in heading_elem.find_next_siblings():
                    sib_text = sibling.get_text(strip=True)
                    if not sib_text:
                        continue
                    if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and \
                       any(k in sib_text for k in section_keywords):
                        break
                    if len(sib_text) > 15:
                        all_parts.append(sib_text)
            combined = '\n'.join(all_parts)
            if len(combined) > 30:
                return _clean_intro_text(combined)

        # 策略3: 关键词定位段落
        for keyword in ['研究方向', '个人简介', '教师简介', '个人介绍']:
            for tag in ['strong', 'b', 'span', 'p', 'div']:
                for elem in soup.find_all(tag):
                    if keyword in elem.get_text(strip=True):
                        intro_parts = []
                        for sibling in [elem] + list(elem.find_next_siblings()):
                            sib_text = sibling.get_text(strip=True)
                            if sib_text and len(sib_text) > 15:
                                if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and \
                                   any(k in sib_text for k in ['简介', '介绍', '经历', '课程', '方向', '成果', '项目', '论文', '奖励']):
                                    if sibling != elem:
                                        break
                                intro_parts.append(sib_text)
                        if intro_parts:
                            combined = '\n'.join(intro_parts)
                            if len(combined) > 30:
                                return _clean_intro_text(combined)

        # 策略4: 提取所有 p 标签段落
        paragraphs = []
        for p in soup.find_all('p'):
            p_text = p.get_text(strip=True)
            if len(p_text) >= 20 and not any(noise in p_text for noise in [
                '首页', 'Copyright', '版权所有', 'ICP备', '联系', '电话', '邮箱',
                '地址', '邮编', '设为首页', '加入收藏', '网站地图', 'Previous',
                'Next', '上一页', '下一页', '更多'
            ]):
                paragraphs.append(p_text)
        if paragraphs:
            combined = '\n'.join(paragraphs)
            return _clean_intro_text(combined)

    except Exception:
        pass
    return ""

def _clean_intro_text(text):
    """清洗简介文本：去除多余空白，保留段落结构，截断至2000字符"""
    if not text:
        return ""
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000] + '...'
    return text

def get_teacher_info(url):
    """详情页高维数据抓取（邮箱、职称、简介）"""
    html_content = get_html(url)
    if not html_content:
        return {"邮箱": "", "职称": "教授", "简介": ""}

    soup = BeautifulSoup(html_content, 'html.parser')
    text = re.sub(r'\s+', ' ', soup.get_text(separator=' '))

    emails = extract_all_emails(html_content, text)
    title = extract_title(text)
    introduction = extract_introduction(soup)

    return {"邮箱": emails, "职称": title, "简介": introduction}

def strip_title_suffix(name):
    """去除教师名字末尾的职称后缀（如教授、讲师等），只保留姓名"""
    title_suffixes = [
        "讲席教授", "特聘教授", "长聘教授", "客座教授", "名誉教授",
        "长聘副教授", "助理教授",
        "高级工程师", "高级实验师",
        "特聘研究员", "特研人员", "副研究员", "助理研究员",
        "博士生导师", "硕士生导师",
        "教授", "副教授", "研究员", "工程师", "实验师", "讲师", "助教"
    ]
    title_suffixes.sort(key=len, reverse=True)
    for suffix in title_suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    return name


def clean_name_noise(name):
    """去除教师姓名中的日期、数字编号等杂余信息，仅保留有效姓名"""
    if not name:
        return name

    # 1. 去除常见日期/数字模式
    noise_patterns = [
        r'\d{4}\s*年\s*(?:[\d一二三四五六七八九十]+\s*月\s*(?:[\d一二三四五六七八九十]+\s*日)?)?',  # 2024年、2024年3月、2024年3月15日
        r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?',  # 2024-03-15、2024/03/15
        r'\d{4}[-/年]\d{1,2}[月]?',               # 2024-03、2024年3月
        r'20\d{2}',                                # 4位数字年份（20开头）
        r'第\s*[\d一二三四五六七八九十百]+\s*[期届批次页]',  # 第一期/届/批/次
        r'[\d一二三四五六七八九十百千]+\s*[号级班节]',      # 1号、2023级、2班
        r'（\s*\d+\s*）',                          # （1）、（ 2 ）
        r'\(\s*\d+\s*\)',                          # (1)、（ 2 ）
        r'\[\s*\d+\s*\]',                          # [1]、[ 2 ]
        r'[\d]+\s*/\s*[\d]+',                      # 2024/2025 等
        r'[\d]+\s*[-–—]\s*[\d]+',                  # 2024-2025 等
    ]

    cleaned = name
    # 先按长度排序降序，避免短模式误伤
    sorted_patterns = sorted(noise_patterns, key=lambda p: len(p), reverse=True)
    for pattern in sorted_patterns:
        cleaned = re.sub(pattern, '', cleaned).strip()

    # 2. 去除开头和结尾的纯数字/符号组合
    cleaned = re.sub(r'^[\s\d\-_—,，、.()（）\[\]【】/\\:：]+', '', cleaned)
    cleaned = re.sub(r'[\s\d\-_—,，、.()（）\[\]【】/\\:：]+$', '', cleaned)

    # 3. 去除多余空格和标点
    cleaned = re.sub(r'[\s\-_—,，、.()（）\[\]【】:：]+', '', cleaned)

    # 4. 如果清洗后为空或太短，返回原名
    if not cleaned or len(cleaned) < 2:
        return name

    # 5. 尝试提取纯中文姓名部分
    chinese_part = re.sub(r'[^\u4e00-\u9fa5]', '', cleaned)
    if chinese_part and len(chinese_part) >= 2 and len(chinese_part) <= 6:
        if chinese_part[0:2] in COMPOUND_SURNAMES or chinese_part[0] in COMMON_SURNAMES:
            return chinese_part

    # 6. 最终校验：如果清洗结果看起来不像姓名，回退原名
    if len(cleaned) >= 2:
        first_chinese = re.sub(r'[^\u4e00-\u9fa5]', '', cleaned)
        if first_chinese and len(first_chinese) >= 2:
            if first_chinese[0:2] in COMPOUND_SURNAMES or first_chinese[0] in COMMON_SURNAMES:
                return first_chinese

    return cleaned

# ============================================================
# 采集主逻辑
# ============================================================
def run_collection():
    """执行采集任务（所有 print 输出会被 GUI 或控制台捕获）"""
    print(f"【程序启动】")

    # IO 独占预检
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'a', encoding='utf-8-sig', newline='') as f:
                pass
        except PermissionError:
            print(f"[错误] CSV文件已被占用，请先关闭：{OUTPUT_FILE}")
            return

    print("正在检索并扩充翻页列表...")
    extended_list_urls = set()
    for start_url in LIST_URLS:
        if start_url.startswith("http"):
            extended_list_urls.update(discover_pagination(start_url))

    print("正在从各列表页提取教师个人主页...")
    all_teacher_links = {}
    extended_list_sorted = sorted(extended_list_urls)
    total_lists = len(extended_list_sorted)

    for l_idx, list_url in enumerate(extended_list_sorted, 1):
        print(f"[列表 {l_idx}/{total_lists}] 正在扫描: {list_url}")
        current_links = extract_teacher_links(list_url)

        page_new_count = 0
        for url, name in current_links.items():
            if url not in all_teacher_links:
                all_teacher_links[url] = name
                page_new_count += 1
                print(f"  -> [发现] {name}: {url}")
        if page_new_count == 0:
            print("  -> 该页未发现新的教师链接")

    total_teachers = len(all_teacher_links)
    if not total_teachers:
        print("[错误] 未检索到任何有效的教师主页链接，请核对配置。")
        return

    print(f"共计发现 {total_teachers} 个主页，开启 {MAX_WORKERS} 线程并发采集")

    last_print_time = [0.0]
    print_interval = 0.2

    results = []
    seen_emails = set()
    stats = {'valid': 0, 'dup': 0, 'none': 0, 'processed': 0}
    lock = threading.Lock()

    def worker(url, name):
        name = strip_title_suffix(name)
        name = clean_name_noise(name)
        info = get_teacher_info(url)
        email_clean = info["邮箱"].strip()

        with lock:
            stats['processed'] += 1
            curr_idx = stats['processed']

            status_str = ""
            if not email_clean:
                stats['none'] += 1
                status_str = "[未获取]"
            elif email_clean in seen_emails:
                stats['dup'] += 1
                status_str = "[重复]"
            else:
                seen_emails.add(email_clean)
                stats['valid'] += 1
                status_str = "[成功]"
                results.append([
                    stats['valid'],
                    name,
                    info["职称"],
                    email_clean,
                    SCHOOL_NAME,
                    COLLEGE_NAME,
                    COLLECTOR_NAME,
                    COLLECT_DATE,
                    info["简介"],
                    url
                ])

            current_time = time.time()
            if curr_idx == total_teachers or curr_idx % 20 == 0 or \
               (current_time - last_print_time[0] > print_interval):
                sys.stdout.write(f"\r已处理: {curr_idx}/{total_teachers} | 当前: {name} -> {status_str}         ")
                sys.stdout.flush()
                last_print_time[0] = current_time

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for url, name in all_teacher_links.items():
            executor.submit(worker, url, name)

    results.sort(key=lambda x: x[0])

    headers = ["序号", "姓名", "职称", "邮箱", "学校", "学院", "采集人",
               "采集日期", "简介", "教师个人主页"]
    try:
        dir_path = os.path.dirname(OUTPUT_FILE)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)

        with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(results)

        print("[完成] 教师数据采集完成")
        print(f"统计汇总 | 发现主页: {total_teachers} | 有效数据: {stats['valid']} "
              f"| 重复剔除: {stats['dup']} | 空白跳过: {stats['none']}")
        print(f"输出路径: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[错误] 写入CSV文件失败: {e}")

# ============================================================
# 图形界面
# ============================================================
class TeaGetGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("教师信息采集工具")

        # 自动检测屏幕分辨率，按横向/竖向设置默认窗口大小
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        if screen_width >= screen_height:
            # 横向屏幕：宽 75%，高 80%
            win_width = int(screen_width * 0.75)
            win_height = int(screen_height * 0.80)
        else:
            # 竖向屏幕：宽 45%，高 35%
            win_width = int(screen_width * 0.45)
            win_height = int(screen_height * 0.35)
        # 确保最小尺寸合理
        win_width = max(win_width, 960)
        win_height = max(win_height, 820)
        self.root.geometry(f"{win_width}x{win_height}")
        self.root.minsize(960, 820)

        self._apply_tk_scaling()

        self.running = False
        self.log_queue = queue.Queue()
        self.old_stdout = None

        # -------- ttkbootstrap 主题美化 --------
        style = ttk.Style(theme="litera")

        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(size=14)
        style.configure(".", font=default_font)
        self.root.option_add("*Font", default_font)

        # 统一日志字体与其他字体一致
        self.log_font = default_font

        main_frame = ttk.Frame(root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---- 标题 ----
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(header_frame, text="教师信息采集工具",
                  font=("Microsoft YaHei", 22, "bold")).pack(anchor=tk.CENTER)

        # ---- 主体内容 ----
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=82)
        content_frame.columnconfigure(1, weight=18)
        content_frame.rowconfigure(0, weight=1)

        # ======== ======== ======== ======== ========
        # 左侧面板：采集配置 + 排除词 + 操作按钮
        # ======== ======== ======== ======== ========
        left_panel = ttk.Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=65)  # 采集配置 65%
        left_panel.rowconfigure(1, weight=35)  # 过滤排除词 35%
        left_panel.rowconfigure(2, weight=0)   # 操作按钮（自然高度）

        # ---------------------- 1. 采集配置 ----------------------
        config_frame = ttk.LabelFrame(left_panel, text=" 采集配置 ")
        config_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=(0, 8))
        config_frame.columnconfigure(0, weight=1)

        config_inner = ttk.Frame(config_frame, padding=16)
        config_inner.grid(row=0, column=0, sticky=tk.NSEW)
        config_inner.columnconfigure(0, weight=1)

        self.form_frame = ttk.Frame(config_inner)
        self.form_frame.pack(fill=tk.BOTH, expand=True)
        self.form_frame.grid_columnconfigure(0, weight=0)
        self.form_frame.grid_columnconfigure(1, weight=1)

        row = 0
        pad = (6, 4)

        # --- 采集人 ---
        ttk.Label(self.form_frame, text="采集人姓名", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        self.collector_var = tk.StringVar(value=COLLECTOR_NAME)
        entry = ttk.Entry(self.form_frame, textvariable=self.collector_var)
        entry.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        row += 1

        # --- 学校 ---
        ttk.Label(self.form_frame, text="学校名称", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        self.school_var = tk.StringVar(value=SCHOOL_NAME)
        entry = ttk.Entry(self.form_frame, textvariable=self.school_var)
        entry.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        row += 1

        # --- 学院 ---
        ttk.Label(self.form_frame, text="学院名称", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        self.college_var = tk.StringVar(value=COLLEGE_NAME)
        entry = ttk.Entry(self.form_frame, textvariable=self.college_var)
        entry.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        row += 1

        # --- URL ---
        ttk.Label(self.form_frame, text="教师列表页 URL", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.NE, padx=pad, pady=4)
        url_frame = ttk.Frame(self.form_frame)
        url_frame.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.NSEW)
        url_frame.columnconfigure(0, weight=1)
        url_frame.rowconfigure(0, weight=1)
        self.url_text = tk.Text(url_frame, height=3, wrap=tk.WORD, font=default_font,
                                relief=tk.FLAT, borderwidth=0, highlightthickness=1,
                                highlightbackground="#ccc", highlightcolor="#0d6efd",
                                padx=8, pady=6)
        self.url_text.insert("1.0", "\n".join(LIST_URLS))
        self.url_text.pack(fill=tk.BOTH, expand=True)
        row += 1

        # --- 输出路径 ---
        ttk.Label(self.form_frame, text="输出文件路径", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        path_frame = ttk.Frame(self.form_frame)
        path_frame.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        path_frame.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar(value=OUTPUT_FILE)
        entry = ttk.Entry(path_frame, textvariable=self.path_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="浏览...", command=self._browse_output, width=8) \
            .pack(side=tk.LEFT, padx=(6, 0))
        row += 1

        # --- 线程数 ---
        ttk.Label(self.form_frame, text="最大线程数", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        worker_row = ttk.Frame(self.form_frame)
        worker_row.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        self.workers_var = tk.IntVar(value=MAX_WORKERS)
        ttk.Spinbox(worker_row, from_=1, to=30,
                     textvariable=self.workers_var, width=6) \
            .pack(side=tk.LEFT)
        ttk.Label(worker_row, text="（建议 5~15）", bootstyle="secondary") \
            .pack(side=tk.LEFT, padx=(8, 0))
        row += 1

        # --- 采集日期 ---
        ttk.Label(self.form_frame, text="采集日期", bootstyle="secondary") \
            .grid(row=row, column=0, sticky=tk.E, padx=pad, pady=4)
        self.date_var = tk.StringVar(value=COLLECT_DATE)
        entry = ttk.Entry(self.form_frame, textvariable=self.date_var)
        entry.grid(row=row, column=1, padx=pad, pady=4, sticky=tk.EW)
        row += 1

        # ---------------------- 2. 过滤排除词（带滚动条，填满剩余高度） ----------------------
        exclude_frame = ttk.LabelFrame(left_panel, text=" 过滤排除词 ")
        exclude_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=(0, 8))
        exclude_frame.columnconfigure(0, weight=1)
        exclude_frame.rowconfigure(0, weight=1)

        exclude_inner = ttk.Frame(exclude_frame, padding=16)
        exclude_inner.grid(row=0, column=0, sticky=tk.NSEW)
        exclude_inner.columnconfigure(0, weight=1)
        exclude_inner.rowconfigure(0, weight=1)

        self.exclude_text = tk.Text(exclude_inner, wrap=tk.WORD, font=default_font,
                                    relief=tk.FLAT, borderwidth=0, highlightthickness=1,
                                    highlightbackground="#ccc", highlightcolor="#0d6efd",
                                    padx=8, pady=6)
        self.exclude_text.insert("1.0", "、".join(EXCLUDE_WORDS))
        self.exclude_text.grid(row=0, column=0, sticky=tk.NSEW)

        exclude_scroll = ttk.Scrollbar(exclude_inner, orient="vertical",
                                        command=self.exclude_text.yview, bootstyle="round")
        self.exclude_text.configure(yscrollcommand=exclude_scroll.set)
        exclude_scroll.grid(row=0, column=1, sticky=tk.NS)

        # ---------------------- 3. 操作按钮 ----------------------
        btn_frame = ttk.Frame(left_panel)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, pady=(0, 0))
        btn_frame.columnconfigure(3, weight=1)

        self.start_btn = ttk.Button(btn_frame, text="启动采集",
                                     command=self._start_collection, bootstyle="success")
        self.start_btn.grid(row=0, column=0, padx=(0, 6))

        self.save_btn = ttk.Button(btn_frame, text="保存配置",
                                    command=self._save_config, bootstyle="info-outline")
        self.save_btn.grid(row=0, column=1, padx=(0, 6))

        self.stop_btn = ttk.Button(btn_frame, text="停止",
                                    command=self._stop_collection,
                                    bootstyle="danger", state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=2, padx=(0, 6))

        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(btn_frame, textvariable=self.progress_var,
                  bootstyle="secondary").grid(row=0, column=3, sticky=tk.E, padx=(6, 0))

        # ======== ======== ======== ======== ========
        # 右侧面板：运行日志
        # ======== ======== ======== ======== ========
        right_panel = ttk.Frame(content_frame)
        right_panel.grid(row=0, column=1, sticky=tk.NSEW, padx=(6, 0))
        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)

        # ---------------------- 4. 运行日志 + 清除按钮 ----------------------
        log_frame = ttk.LabelFrame(right_panel, text=" 运行日志 ")
        log_frame.grid(row=0, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        log_inner = ttk.Frame(log_frame, padding=12)
        log_inner.grid(row=0, column=0, sticky=tk.NSEW)
        log_inner.columnconfigure(0, weight=1)
        log_inner.rowconfigure(1, weight=1)

        # 标题行（清除按钮）
        log_header = ttk.Frame(log_inner)
        log_header.grid(row=0, column=0, sticky=tk.EW, pady=(0, 6))
        log_header.columnconfigure(0, weight=1)

        ttk.Label(log_header, text="运行日志",
                  font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky=tk.W)

        self.clear_log_btn = ttk.Button(log_header, text="清除",
                                         command=self._clear_log, bootstyle="secondary-outline", width=6)
        self.clear_log_btn.grid(row=0, column=1, sticky=tk.E, padx=(6, 0))

        # 日志文本框
        log_body = ttk.Frame(log_inner)
        log_body.grid(row=1, column=0, sticky=tk.NSEW)
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_body, wrap=tk.WORD, state=tk.DISABLED,
                                relief=tk.FLAT, borderwidth=0, highlightthickness=1,
                                highlightbackground="#ddd", highlightcolor="#0d6efd",
                                padx=8, pady=6)
        log_scroll = ttk.Scrollbar(log_body, orient="vertical",
                                    command=self.log_text.yview, bootstyle="round")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.configure(font=default_font)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        log_scroll.grid(row=0, column=1, sticky=tk.NS)

        # 轮询日志队列
        self.root.after(200, self._poll_log)

    # --------------- 高分屏缩放 ---------------

    def _apply_tk_scaling(self):
        """ttkbootstrap / tkinter 高分屏适配"""
        try:
            import ctypes
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            ctypes.windll.user32.ReleaseDC(0, hdc)
            scale = dpi / 96.0
            if abs(scale - 1.0) > 0.05:
                self.root.tk.call('tk', 'scaling', scale)
        except Exception:
            pass

    # --------------- 辅助 ---------------

    def _browse_output(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        initial_dir = os.path.dirname(os.path.abspath(self.path_var.get()))
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            initialdir=initial_dir if os.path.exists(initial_dir) else script_dir,
            initialfile=os.path.basename(self.path_var.get())
        )
        if path:
            self.path_var.set(path)

    def _clear_log(self):
        """清除日志内容"""
        if self.log_text is None:
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_log(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._log(msg)
        self.root.after(200, self._poll_log)

    # --------------- 保存配置 ---------------

    def _save_config(self):
        """将 GUI 中的配置保存到 JSON 文件并更新全局变量"""
        global COLLECTOR_NAME, SCHOOL_NAME, COLLEGE_NAME, LIST_URLS
        global OUTPUT_FILE, MAX_WORKERS, COLLECT_DATE, EXCLUDE_WORDS, EXCLUDE_REGEX

        # 从 GUI 读取
        COLLECTOR_NAME = self.collector_var.get().strip()
        SCHOOL_NAME = self.school_var.get().strip()
        COLLEGE_NAME = self.college_var.get().strip()
        LIST_URLS = [u.strip() for u in self.url_text.get("1.0", tk.END).strip().splitlines() if u.strip()]
        OUTPUT_FILE = self.path_var.get().strip()
        MAX_WORKERS = self.workers_var.get()

        date_val = self.date_var.get().strip()
        if date_val:
            COLLECT_DATE = date_val

        # 解析排除词（顿号/逗号/换行分隔）
        raw_exclude = self.exclude_text.get("1.0", tk.END).strip()
        if raw_exclude:
            EXCLUDE_WORDS = [w.strip() for w in re.split(r'[、，, \n]+', raw_exclude) if w.strip()]
            EXCLUDE_REGEX = re.compile('|'.join(map(re.escape, EXCLUDE_WORDS)), re.IGNORECASE)

        # 持久化到 JSON
        save_config_to_json()

        self._log("✅ 配置已保存")

    # --------------- 启动采集 ---------------

    def _start_collection(self):
        if self.running:
            return

        # 校验
        if not self.collector_var.get().strip():
            messagebox.showwarning("提示", "请输入采集人姓名")
            return
        if not self.school_var.get().strip():
            messagebox.showwarning("提示", "请输入学校名称")
            return
        if not self.college_var.get().strip():
            messagebox.showwarning("提示", "请输入学院名称")
            return
        urls = [u.strip() for u in self.url_text.get("1.0", tk.END).strip().splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("提示", "请至少输入一个教师列表页 URL")
            return
        if self.workers_var.get() < 1:
            messagebox.showwarning("提示", "线程数必须 ≥ 1")
            return

        # 先保存配置
        self._save_config()

        # 清空日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set("运行中...")

        self.thread = threading.Thread(target=self._run_task, daemon=True)
        self.thread.start()

    def _run_task(self):
        """后台线程：重定向 stdout 并运行采集逻辑"""
        self.old_stdout = sys.stdout
        sys.stdout = LogCapture(self.log_queue.put)
        try:
            run_collection()
            self.log_queue.put("")
            self.log_queue.put("=" * 50)
            self.log_queue.put("✅ 采集任务完成！")
        except Exception as e:
            self.log_queue.put(f"❌ 采集过程异常：{e}")
        finally:
            sys.stdout = self.old_stdout
            self.old_stdout = None
            self.root.after(0, self._on_finish)

    def _on_finish(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_var.set("就绪")

    def _stop_collection(self):
        """停止：强制退出进程（子线程无法安全终止，告知用户）"""
        self._log("■ 用户请求停止（当前线程完成后自动停止）")
        # 在现有架构中无法安全强行终止线程池，只能标记
        self.running = False
        self._on_finish()

# ============================================================
# 入口
# ============================================================
if __name__ == '__main__':
    # Windows 下确保 stdout 编码为 UTF-8
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    # 命令行模式：python TeaGet.py --cli
    if "--cli" in sys.argv:
        run_collection()
    else:
        root = tk.Tk()
        app = TeaGetGUI(root)
        root.mainloop()
