import requests
from bs4 import BeautifulSoup
import csv
import re
import urllib.parse
import urllib3
import os
import html
import threading
import sys  
import time  
from concurrent.futures import ThreadPoolExecutor

# 导入配置参数
from Config import (
    SCHOOL_NAME, COLLEGE_NAME, LIST_URLS, OUTPUT_FILE, 
    MAX_WORKERS, EXCLUDE_REGEX, COMMON_SURNAMES, COMPOUND_SURNAMES,
    COLLECTOR_NAME, COLLECT_DATE
)

def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
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
        if any(re.search(pat, href, re.IGNORECASE) for pat in page_patterns) or any(x in text for x in ['下一页', '尾页', '末页']):
            discovered_urls.add(urllib.parse.urljoin(base_url, href))
            
    return list(discovered_urls)

def decode_cloudflare_email(cf_string):
    """解密Cloudflare混淆保护的邮箱"""
    try:
        if not cf_string: return ""
        hex_num = int(cf_string[:2], 16)
        return ''.join([chr(int(cf_string[i:i+2], 16) ^ hex_num) for i in range(2, len(cf_string), 2)])
    except Exception:
        return ""

def extract_all_emails(html_content, text_content):
    """邮箱清洗与还原"""
    if not html_content: return ""
    
    html_content = html.unescape(html_content)
    soup = BeautifulSoup(html_content, 'html.parser')
    found_emails = []
    
    def add_email(email_str):
        email_str = email_str.strip().strip('.').lower()
        email_str = re.sub(r'\s+', '', email_str)
        if email_str and '@' in email_str and email_str not in found_emails:
            if re.match(r'^[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10}$', email_str):
                found_emails.append(email_str)

    # 1. Cloudflare安全节点探测与解密
    for cf_tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded = decode_cloudflare_email(cf_tag['data-cfemail'])
        if decoded: add_email(decoded)
        
    for a_cf in soup.find_all('a', href=re.compile(r'cdn-cgi/l/email-protection', re.IGNORECASE)):
        match = re.search(r'#([a-fA-F0-9]+)', a_cf.get('href', ''))
        if match:
            decoded = decode_cloudflare_email(match.group(1))
            if decoded: add_email(decoded)

    # 2. 标准Mailto协议提取
    for a in soup.find_all('a', href=re.compile(r'^mailto:', re.IGNORECASE)):
        match = re.search(r'mailto:\s*([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,10})', urllib.parse.unquote(a['href']), re.IGNORECASE)
        if match: add_email(match.group(1))

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
        if not any(x in email_lower for x in ['office', 'admin', 'master', 'system', 'xyw', 'nic@', 'library', 'postmaster', 'baoming', 'advice']):
            return email 
    return ""

def looks_like_name(text):
    """姓氏字典姓名校验"""
    text = text.strip()
    if not text or len(text) < 2 or len(text) > 20: return False
    
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
    titles = ["讲席教授", "特聘教授", "长聘教授", "客座教授", "名誉教授", "长聘副教授", "助理教授", "副教授", "教授", "高级工程师", "工程师", "高级实验师", "实验师", "特聘研究员", "特研人员", "副研究员", "助理研究员", "研究员", "博士生导师", "硕士生导师", "讲师", "助教"]
    text = text.replace(" ", "").replace("\n", "").replace("\r", "")
    # 按长度降序排列，避免"副教授"被"教授"子串误匹配
    titles.sort(key=len, reverse=True)
    for title in titles:
        if title in text: return title
        
    return "教授"

def extract_teacher_links(list_url):
    """列表页解析定位"""
    html_content = get_html(list_url)
    if not html_content: return {}
        
    teacher_links = {}
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for a in soup.find_all('a'):
        a_href = a.get('href')
        a_text = a.get_text(strip=True)
        if not a_href or not a_text: continue
        
        full_url = urllib.parse.urljoin(list_url, a_href)
        if full_url.startswith(('mailto:', 'javascript:')) or full_url.lower().endswith(('.jpg', '.png', '.pdf', '.doc', '.docx', '.xlsx', '.xls')):
            continue
            
        name_extracted = next((cand for cand in [a.get('title', '').strip(), a_text] + list(a.stripped_strings) if cand and looks_like_name(cand)), None)
        if name_extracted and full_url not in teacher_links:
            teacher_links[full_url] = name_extracted
                
    return teacher_links

def extract_introduction(soup):
    """从教师详情页提取个人简介文本（含研究方向、科研成果等多章节内容）"""
    try:
        # ========== 策略1: 尝试找到主内容容器 ==========
        # 高校教师页常用容器选择器（按可靠性排序）
        intro_selectors = [
            # 最精确的容器选择器（先尝试最具体的）
            'div.wp_articlecontent', 'div.entry', 'div.read', 'div.articlecontent',
            # 通用文章/内容容器
            'div.article-content', 'div.article', 'div.content', 'div.main-content',
            'div.entry-content', 'div.wp-content', 'div.post-content', 'div.page-content',
            # 教师简介专用容器
            'div.intro', 'div.teacher-intro', 'div.teacher-info', 'div.teacher_detail',
            'div.teacher_info', 'div.profile', 'div.personal-info', 'div.info',
            # 兜底容器
            'div.text', 'div.contain', 'div.main', 'div.body',
            # ID选择器
            '#content', '#article', '#main', '#page-content', '#con', '#neirong'
        ]
        for selector in intro_selectors:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator='\n', strip=True)
                if len(text) > 30:
                    return _clean_intro_text(text)
        
        # ========== 策略2: 按章节标题收集所有内容段落 ==========
        # 收集所有匹配章节标题的<h>元素
        section_keywords = [
            '个人简介', '教师简介', '个人介绍', '教师介绍', '基本信息',
            '个人概况', '个人经历', '工作经历', '教育经历', '教学情况',
            '研究方向', '主讲课程', '学术成果', '科研项目', '科研成果',
            '论文成果', '代表论著', '学术兼职', '社会兼职', '荣誉奖励',
            '获奖情况', '专利情况', '著作论文'
        ]
        
        # 收集页面中所有可能的章节标题元素
        all_sections = []  # [(heading_elem, heading_text), ...]
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            for elem in soup.find_all(tag):
                heading_text = elem.get_text(strip=True)
                if any(kw in heading_text for kw in section_keywords):
                    all_sections.append((elem, heading_text))
        
        # 按文档顺序排序
        all_sections.sort(key=lambda x: x[0].sourcepos if hasattr(x[0], 'sourcepos') else 0)
        
        if all_sections:
            # 如果找到了章节标题，提取每个章节下的内容段落
            all_parts = []
            for i, (heading_elem, heading_text) in enumerate(all_sections):
                # 包含章节标题本身
                all_parts.append(heading_text)
                # 提取该章节下的内容（直到下一个同层级标题或文档结束）
                for sibling in heading_elem.find_next_siblings():
                    sib_text = sibling.get_text(strip=True)
                    if not sib_text:
                        continue
                    # 如果遇到另一个<h>标题且包含关键词，停止（交给下一个章节处理）
                    if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and any(
                        k in sib_text for k in section_keywords):
                        break
                    if len(sib_text) > 15:
                        all_parts.append(sib_text)
            
            combined = '\n'.join(all_parts)
            if len(combined) > 30:
                return _clean_intro_text(combined)
        
        # 如果没有明确章节标题，尝试查找"研究方向"等关键词直接定位段落
        for keyword in ['研究方向', '个人简介', '教师简介', '个人介绍']:
            for tag in ['strong', 'b', 'span', 'p', 'div']:
                for elem in soup.find_all(tag):
                    if keyword in elem.get_text(strip=True):
                        intro_parts = []
                        # 从该元素及其后续兄弟提取内容
                        for sibling in [elem] + list(elem.find_next_siblings()):
                            sib_text = sibling.get_text(strip=True)
                            if sib_text and len(sib_text) > 15:
                                if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and any(
                                    k in sib_text for k in ['简介', '介绍', '经历', '课程', '方向', '成果', '项目', '论文', '奖励']):
                                    if sibling != elem:
                                        break
                                intro_parts.append(sib_text)
                        if intro_parts:
                            combined = '\n'.join(intro_parts)
                            if len(combined) > 30:
                                return _clean_intro_text(combined)
        
        # ========== 策略3: 提取所有p标签段落，过滤噪音文本 ==========
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
    # 保留段落间的换行，但去除连续空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    max_len = 2000
    if len(text) > max_len:
        text = text[:max_len] + '...'
    return text

def get_teacher_info(url):
    """详情页高维数据抓取（邮箱、职称、简介）"""
    html_content = get_html(url)
    if not html_content: return {"邮箱": "", "职称": "教授", "简介": ""}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    text = re.sub(r'\s+', ' ', soup.get_text(separator=' '))
    
    emails = extract_all_emails(html_content, text)
    title = extract_title(text)
    introduction = extract_introduction(soup)
    
    return {"邮箱": emails, "职称": title, "简介": introduction}

def strip_title_suffix(name):
    """去除教师名字末尾的职称后缀（如教授、讲师等），只保留姓名"""
    # 职称后缀列表，按长度降序排列以避免短后缀误伤
    title_suffixes = [
        "讲席教授", "特聘教授", "长聘教授", "客座教授", "名誉教授",
        "长聘副教授", "助理教授",
        "高级工程师", "高级实验师",
        "特聘研究员", "特研人员", "副研究员", "助理研究员",
        "博士生导师", "硕士生导师",
        "教授", "副教授", "研究员", "工程师", "实验师", "讲师", "助教"
    ]
    # 按长度降序排列
    title_suffixes.sort(key=len, reverse=True)
    
    for suffix in title_suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    return name

def main():
    print(f"【程序启动】")

    # IO独占预检
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'a', encoding='utf-8-sig', newline='') as f: pass
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
    extended_list_sorted = sorted(list(extended_list_urls))
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
        # 去除教师姓名中的职称后缀（如"王某某教授" -> "王某某"）
        name = strip_title_suffix(name)
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
                status_str = f"[成功]"
                
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
            if curr_idx == total_teachers or curr_idx % 20 == 0 or (current_time - last_print_time[0] > print_interval):
                sys.stdout.write(f"\r已处理: {curr_idx}/{total_teachers} | 当前: {name} -> {status_str}         ")
                sys.stdout.flush()
                last_print_time[0] = current_time

    # 提交多线程并发任务池
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for url, name in all_teacher_links.items():
            executor.submit(worker, url, name)

    # 修正乱序
    results.sort(key=lambda x: x[0])

    # 导出 CSV
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
        print(f"统计汇总 | 发现主页: {total_teachers} | 有效数据: {stats['valid']} \
               | 重复剔除: {stats['dup']} | 空白跳过: {stats['none']}")
        print(f"输出路径: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[错误] 写入CSV文件失败: {e}")

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    main()
