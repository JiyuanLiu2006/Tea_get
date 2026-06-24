# TeaGet Terminal — 高校教师信息采集工具（终端版）

一个基于**Python**的高校教师信息自动采集工具，支持从高校官网教师列表页自动抓取教师姓名、职称、邮箱、个人简介等信息，并导出为 CSV 文件。


## 系统要求

- Python **3.8** 或更高版本
- Windows 7 及以上（已测试 Windows 10/11）或MacOS 10.14及以上（已测试MacOS 15/26/27）
- 网络连接正常

## 依赖库

`requests` | ≥ 2.25 
`beautifulsoup4` | ≥ 4.9 
`urllib3` | ≥ 1.26 
`lxml` | ≥ 4.6 

### 安装依赖

```bash
pip install requests beautifulsoup4 urllib3
```



## 配置方法

所有配置集中在 `Config.py` 文件中，打开后修改以下参数：

### 必填配置

```python
# 采集人姓名（显示在 CSV 中）
COLLECTOR_NAME = "张三"

# 学校名称
SCHOOL_NAME = "西安财经大学"

# 学院名称
COLLEGE_NAME = "统计与数据科学学院"

# 教师列表页 URL（可配置多个起始页）
LIST_URLS = [
    "https://tongji.xaufe.edu.cn/info/1062/2814.htm",
    "https://example.edu.cn/teacher/list.htm"
]
```

### 可选配置

```python
# CSV 输出路径（默认在当前目录）
OUTPUT_FILE = "采集结果.csv"

# 并发线程数（建议 5-15，根据网络和网站限制调整）
MAX_WORKERS = 15
```


## 使用规则

### 基本用法

1. 编辑 `Config.py` 填入目标网站信息
2. 运行主程序：

```bash
python Teaget-main.py
```

3. 等待采集完成，结果自动写入 `采集结果.csv`


## 注意事项

### 合法合规

- **请遵守目标网站的 `robots.txt` 和使用条款**，仅在允许范围内采集
- **合理控制请求频率**，建议 `MAX_WORKERS` 设置为 5-10，避免对目标服务器造成压力
- **仅用于合法用途**，如学术研究、信息公开等
- 本工具仅采集已公开的教师信息，不涉及任何非公开数据

### 技术提示

- 部分网站可能对爬虫有反爬机制（如 IP 限流、验证码），如遇到大规模失败可降低 `MAX_WORKERS`
- 若网站使用了特殊的前端渲染（JavaScript 动态加载），本工具无法抓取，需配合 Selenium 等工具
- CSV 文件默认使用 UTF-8 BOM 编码，Excel 可直接打开；如乱码请用 WPS 或 VS Code 打开

