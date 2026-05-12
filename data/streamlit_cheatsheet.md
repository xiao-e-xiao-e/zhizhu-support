# Streamlit 速查手册

## 安装与启动

```bash
pip install streamlit
streamlit run app.py
```

## 文本显示

| 函数 | 用途 | 示例 |
|------|------|------|
| `st.title()` | 页面标题 | `st.title("My App")` |
| `st.header()` | 区块标题 | `st.header("Section")` |
| `st.subheader()` | 子标题 | `st.subheader("Sub")` |
| `st.text()` | 纯文本 | `st.text("Hello")` |
| `st.markdown()` | Markdown 渲染 | `st.markdown("**bold**")` |
| `st.code()` | 代码块 | `st.code("x = 1", "python")` |
| `st.caption()` | 小字说明 | `st.caption("footnote")` |
| `st.latex()` | 数学公式 | `st.latex(r"e^{i\pi}+1=0")` |

## 数据展示

### 表格
- `st.dataframe(df)` — 交互式表格，支持排序和筛选
- `st.table(df)` — 静态表格
- `st.json(data)` — JSON 展示
- `st.metric(label, value, delta)` — 指标卡片

### 图表
Streamlit 原生支持多种图表库：
- `st.line_chart(data)` — 折线图
- `st.area_chart(data)` — 面积图
- `st.bar_chart(data)` — 柱状图
- `st.map(data)` — 地图（需经纬度列）
- Altair、Plotly、Matplotlib 也可直接渲染

## 输入组件

### 文本输入
- `st.text_input("标签", placeholder="提示")` — 单行文本
- `st.text_area("标签")` — 多行文本
- `st.number_input("标签", min_value=0, max_value=100)` — 数字
- `st.chat_input("提示")` — 聊天输入框

### 选择组件
- `st.button("点击")` — 按钮
- `st.selectbox("选择", options)` — 单选下拉
- `st.multiselect("多选", options)` — 多选下拉
- `st.radio("单选", options)` — 单选按钮组
- `st.checkbox("勾选")` — 复选框
- `st.toggle("开关")` — 开关切换
- `st.slider("滑块", 0, 100, 50)` — 滑块

### 文件上传
- `st.file_uploader("上传", type=["pdf", "csv"])` — 支持单/多文件
- `st.camera_input("拍照")` — 调用摄像头

## 布局

- `st.sidebar` — 侧边栏上下文管理器
- `st.columns(n)` — 多列布局
- `st.tabs(["标签1", "标签2"])` — 标签页
- `st.expander("展开查看")` — 折叠面板
- `st.container()` — 通用容器
- `st.empty()` — 占位符（可后续填充）

## 状态管理

### Session State
```python
if "counter" not in st.session_state:
    st.session_state.counter = 0

if st.button("+1"):
    st.session_state.counter += 1
```

### 缓存
- `@st.cache_data` — 缓存数据（数据库查询、API 调用等）
- `@st.cache_resource` — 缓存资源（数据库连接、模型加载等）

## 状态提示

- `st.spinner("加载中...")` — 加载动画
- `st.progress(value)` — 进度条
- `st.toast("提示消息")` — 浮动提示
- `st.success("成功")` / `st.error("错误")` / `st.warning("警告")` / `st.info("信息")`

## 常用模式

### 表单（批量提交）
```python
with st.form("my_form"):
    name = st.text_input("姓名")
    submitted = st.form_submit_button("提交")
    if submitted:
        st.success(f"你好 {name}")
```

### 对话框
```python
@st.dialog("确认")
def confirm():
    st.write("确定要删除吗？")
    if st.button("确定"):
        st.session_state.deleted = True
        st.rerun()
```

### 页面配置
```python
st.set_page_config(
    page_title="标题",
    page_icon="🦊",
    layout="wide",        # 或 "centered"
    initial_sidebar_state="expanded",  # 或 "collapsed"
)
```

## Streamlit 与 AI 应用的天然契合

Streamlit 是构建 AI 应用原型的首选框架，原因如下：
1. 热重载：修改代码自动刷新，所见即所得
2. 与 Python 数据科学生态无缝集成（Pandas、NumPy、Plotly）
3. 内置聊天组件 `st.chat_message` 和 `st.chat_input`
4. 一行命令即可部署到 Streamlit Cloud
5. 支持环境变量管理敏感的 API Key
