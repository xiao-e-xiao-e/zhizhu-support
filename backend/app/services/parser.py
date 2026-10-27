"""文档解析模块：多格式文本提取 + 段落感知分块。

修复的缺陷（第 5 个，原实现中未被察觉）：
    各解析器原本统一用 "\\n".join 拼接结果，而 chunk_text 按 "\\n\\n" 切分段落。
    这意味着解析产物里根本不存在空行，`text.split("\\n\\n")` 永远只得到一个元素，
    于是「按段落边界切分」从未生效——所有文档都退化成按字符数硬切，
    分块器里那段段落合并逻辑（chunk_text 的 for para in paragraphs 循环）
    实际上是一段死代码。本版统一用 "\\n\\n" 作为段落分隔符。

另一处修复：Markdown 解析原本直接删掉 ``` 代码块与 ` 行内代码，
    对技术文档等于把最该被检索的内容扔了。本版只去除围栏标记，保留代码正文。
"""
from __future__ import annotations

import csv as csv_module
import re
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path

PARAGRAPH_SEP = "\n\n"


# ============ 文本提取 ============

class _HTMLTextExtractor(HTMLParser):
    """从 HTML 中提取纯文本。

    原实现靠 `get_starttag_text()` 判断当前是否处于 script/style 内，
    但该方法返回的是「最近一次出现的开始标签文本」，并不表示当前节点位置，
    遇到嵌套结构会判断错误。本版改为维护跳过深度计数器。
    """

    _SKIP_TAGS = {"script", "style", "noscript", "head", "title"}

    # 块级标签：作为段落边界。pre / code 不在其中，代码正文需要保留
    _BLOCK_TAGS = {
        "p", "div", "section", "article", "aside", "header", "footer", "main",
        "nav", "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody",
        "tr", "td", "th", "blockquote", "figure", "figcaption",
        "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocks: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0

    def _flush(self) -> None:
        text = " ".join(self._buffer).strip()
        if text:
            self._blocks.append(text)
        self._buffer.clear()

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in self._BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._buffer.append(text)

    def get_text(self) -> str:
        self._flush()
        return PARAGRAPH_SEP.join(self._blocks)


def parse_pdf(file_bytes: bytes) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(BytesIO(file_bytes))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    return PARAGRAPH_SEP.join(pages)


def parse_docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(BytesIO(file_bytes))
    blocks: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    return PARAGRAPH_SEP.join(blocks)


def parse_html(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8", errors="replace")
    extractor = _HTMLTextExtractor()
    extractor.feed(text)
    return extractor.get_text()


def parse_csv(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv_module.reader(StringIO(text))
    rows: list[str] = []
    for row in reader:
        if row:
            cells = [cell.strip() for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
    return PARAGRAPH_SEP.join(rows)


def parse_markdown(text: str) -> str:
    """剥离 Markdown 标记，但保留正文与代码内容。"""
    # 去掉代码围栏行本身，保留围栏内的代码
    text = re.sub(r"^[ \t]*```[^\n]*$", "", text, flags=re.MULTILINE)
    # 行内代码只去掉反引号
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    # 标题标记
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 图片整体丢弃，链接保留文字
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]*)\]\(.*?\)", r"\1", text, flags=re.DOTALL)
    # 强调标记
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # 列表与引用标记
    text = re.sub(r"^[ \t]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    # 分隔线整行丢弃
    text = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "", text, flags=re.MULTILINE)
    # 压缩多余空行
    text = re.sub(r"\n{3,}", PARAGRAPH_SEP, text)
    return text.strip()


# ============ 文本分块 ============

def _split_paragraphs(text: str) -> list[str]:
    """按空行切段落，容忍行尾空白与 \r\n。"""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[str]:
    """按段落聚合分块，尽量保持段落完整。

    短段落会合并进同一个块直到接近 chunk_size；
    单个超长段落（没有空行的大段文本）退化为带重叠的滑动窗口切分。
    """
    if not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append(PARAGRAPH_SEP.join(current))
            current = []
            current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            # 超长段落单独处理，先收尾已有内容
            flush()
            step = max(50, chunk_size - chunk_overlap)
            for i in range(0, len(para), step):
                piece = para[i : i + chunk_size]
                if piece.strip():
                    chunks.append(piece)
            continue

        if current_len + len(para) <= chunk_size:
            current.append(para)
            current_len += len(para) + len(PARAGRAPH_SEP)
        else:
            flush()
            current = [para]
            current_len = len(para)

    flush()
    return chunks


# ============ 主入口 ============

def extract_text(filename: str, file_bytes: bytes) -> str:
    """提取文件中的纯文本（不切块），用于预览。"""
    ext = Path(filename).suffix.lower()

    parsers = {
        ".pdf": parse_pdf,
        ".docx": parse_docx,
        ".html": parse_html,
        ".htm": parse_html,
        ".csv": parse_csv,
    }

    if ext in parsers:
        return parsers[ext](file_bytes)

    text = file_bytes.decode("utf-8", errors="replace")
    if ext in (".md", ".markdown"):
        return parse_markdown(text)
    return text.strip()


def parse_file(
    filename: str,
    file_bytes: bytes,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[str]:
    """解析文件并返回 chunk 列表。"""
    text = extract_text(filename, file_bytes)
    if not text:
        return []
    return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
