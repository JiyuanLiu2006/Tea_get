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
    titles = ["讲席教授", "特聘教授", "长聘教授", "客座教授", "名誉教授", "长聘副教授", "教授", "副教授", "助理教授", "高级工程师", "工程师", "高级实验师", "实验师", "特聘研究员", "特研人员", "副研究员", "助理研究员", "研究员", "讲师", "助教", "博士生导师", "硕士生导师"]
    text = text.replace(" ", "").replace("\n", "").replace("\r", "")
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

def get_teacher_info(url):
    """详情页高维数据抓取"""
    html_content = get_html(url)
    if not html_content: return {"邮箱": "", "职称": "教授"}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    text = re.sub(r'\s+', ' ', soup.get_text(separator=' '))
    
    emails = extract_all_emails(html_content, text)
    title = extract_title(text)
    
    return {"邮箱": emails, "职称": title}

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
                    "",              
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
