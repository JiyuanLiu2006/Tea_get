# TeaGet — 高校教师信息采集工具（图形化版）

一个基于**Python**的图形化高校教师信息自动采集工具，支持从高校官网教师列表页自动抓取教师姓名、职称、邮箱、个人简介等信息，并导出为 CSV 文件。


## 依赖库

### 核心依赖


`requests` | ≥ 2.25 
`beautifulsoup4` | ≥ 4.9 
`urllib3` | ≥ 1.26 
`ttkbootstrap` | ≥ 1.5 
`lxml` | ≥ 4.6 

### 系统要求

- Python **3.8** 或更高版本
- Windows 7 及以上（已测试 Windows 10/11） MacOS暂未做测试，适配性未知
- 网络连接正常

### 安装依赖
```bash
pip install requests beautifulsoup4 urllib3 ttkbootstrap lxml
```


## 配置方法

### 方式一：通过 GUI 界面配置（推荐）

1. 运行程序，在 **采集配置** 面板中填写以下信息：

   | 配置项 | 说明 | 示例 |
   |--------|------|------|
   | 采集人姓名 | 您的姓名 | `张三` |
   | 学校名称 | 学校全称 | `西安财经大学` |
   | 学院名称 | 学院全称 | `信息学院` |
   | 教师列表页 URL | 每行一个链接，支持多个 | `https://xxx.edu.cn/szdw1.htm` |
   | 输出文件路径 | CSV 保存位置 | `D:\data\采集结果.csv` |
   | 最大线程数 | 并发采集线程数 | `15` |
   | 采集日期 | 数据采集日期 | `2026/06/24` |

2. 在 **过滤排除词** 面板中，用顿号（`、`）分隔不需要抓取的关键词（如"首页"、"通知公告"等）。

3. 点击 **保存配置** 按钮，配置会被持久化到 `config.json` 中。

4. 点击 **启动采集** 开始数据采集。

### 方式二：直接编辑 config.json

程序启动时会自动读取同目录下的 `config.json` 文件。你也可以手动编辑该文件：

```json
{
  "collector_name": "张三",
  "school_name": "西安财经大学",
  "college_name": "信息学院",
  "list_urls": [
    "https://xinxi.xaufe.edu.cn/jsfc1/dzswx1.htm",
    "https://xinxi.xaufe.edu.cn/jsfc1/wlgcx1.htm"
  ],
  "output_file": "D:\\Tea_Get_GUI\\采集结果.csv",
  "max_workers": 15,
  "collect_date": "2026/06/24",
  "exclude_words": [
    "首页", "上一页", "下一页", "通知公告", "新闻",
    "概况", "师资", "招生", "就业", "科研"
  ]
}
```

| 配置键 | 类型 | 说明 |
|--------|------|------|
| `collector_name` | string | 采集人姓名 |
| `school_name` | string | 学校名称 |
| `college_name` | string | 学院名称 |
| `list_urls` | string[] | 教师列表页 URL 数组 |
| `output_file` | string | 输出 CSV 文件完整路径 |
| `max_workers` | int | 最大并发线程数（1~30） |
| `collect_date` | string | 采集日期（格式：YYYY/MM/DD） |
| `exclude_words` | string[] | 排除关键词列表（用于过滤非教师链接） |

---


### 注意事项

1. **网络环境**：确保网络连接稳定，部分高校网站可能需要校园网环境才能访问。
2. **SSL 证书**：程序已默认禁用 SSL 证书验证（`verify=False`），以兼容部分配置不规范的网站。
3. **反爬策略**：请适度使用，设置合理的线程数（建议 ≤15），避免对目标服务器造成压力。
4. **编码问题**：CSV 文件使用 `UTF-8 with BOM`（`utf-8-sig`）编码，可直接用 Excel 打开而不会出现乱码。
5. **权限问题**：如果 CSV 文件正在被 Excel 打开，程序会提示错误，请先关闭文件再重新采集。
6. **邮箱隐私**：部分网站使用 Cloudflare 邮箱保护或中文混淆，程序已内置解密支持，但仍可能有部分邮箱无法识别。
7. **姓名校验**：程序使用内置的姓氏字典（单姓 + 复姓）进行姓名识别，如果遇到未收录的姓氏，请修改代码中的 `COMMON_SURNAMES` 或 `COMPOUND_SURNAMES` 字典。

### 停止操作

点击 **停止** 按钮，当前正在处理的线程完成后自动停止。


## 本项目仅供学习与研究使用。使用者应遵守相关法律法规及目标网站的 `robots.txt` 协议，合理使用本工具。
