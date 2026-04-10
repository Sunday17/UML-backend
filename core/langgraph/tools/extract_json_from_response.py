import re
import json


def extract_json_from_response(res):
    """
    从响应字符串中提取 JSON 字符串片段（不负责 json.loads）。

    兼容：
    - ```json ... ``` / ``` ... ``` 代码块
    - 前后带解释文字
    - 既可能是对象 `{}` 也可能是数组 `[]`
    """
    if res is None:
        raise ValueError("响应为空 (None)")

    if not isinstance(res, str):
        # 兼容少量 SDK/封装层直接返回 dict/list 的情况
        try:
            return json.dumps(res, ensure_ascii=False)
        except Exception:
            raise ValueError(f"响应类型不是字符串，且无法序列化为 JSON: {type(res)}")

    text = res.strip()
    if not text:
        raise ValueError("响应为空字符串")

    # 1) 优先：```json ... ```
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 2) 其次：任意 ```...``` 代码块（有些模型不写 json 标签）
    m = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if m and m.group(1).strip():
        candidate = m.group(1).strip()
        # 若代码块里夹杂语言标签（极少数会写成 ```\njson\n{...}）尝试剥离第一行
        first_line, _, rest = candidate.partition("\n")
        if first_line.strip().lower() in {"json", "javascript", "js"} and rest.strip():
            return rest.strip()
        return candidate

    # 3) 最后：从全文里截取最像 JSON 的片段（对象或数组）
    candidates = []
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1].strip())

    # 4) 更激进：匹配所有 {...} 或 [...] 片段，按长度从大到小尝试
    #    说明：这里不做完整括号平衡解析，交由 parse_json_from_response 再逐个 json.loads 验证
    candidates.extend(re.findall(r"\{[\s\S]*\}", text))
    candidates.extend(re.findall(r"\[[\s\S]*\]", text))

    candidates = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
    # 去重（保持顺序）
    seen = set()
    uniq = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    if uniq:
        # 返回最长的，通常包含最完整结构
        return max(uniq, key=len)

    raise ValueError("未找到有效的 JSON 内容")


def parse_json_from_response(res):
    """
    从响应中解析出 JSON 对象（dict/list）。

    相比直接 json.loads(res)，会先抽取潜在 JSON 片段，并对多个候选片段逐个尝试。
    """
    if isinstance(res, (dict, list)):
        return res

    text = res if isinstance(res, str) else None
    extracted = extract_json_from_response(res)

    # 先尝试最可信的 extracted
    try:
        return json.loads(extracted)
    except Exception:
        pass

    # 再尝试从全文提取到的多个片段（extract_json_from_response 内部已做过一些收敛，
    # 这里再从原文里穷举若干候选，以提升成功率）
    if isinstance(text, str):
        raw = text.strip()
        pool = []
        pool.extend(re.findall(r"```json\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE))
        pool.extend(re.findall(r"```\s*([\s\S]*?)\s*```", raw))
        pool.extend(re.findall(r"\{[\s\S]*\}", raw))
        pool.extend(re.findall(r"\[[\s\S]*\]", raw))
        pool = [p.strip() for p in pool if isinstance(p, str) and p.strip()]
        pool.sort(key=len, reverse=True)

        for cand in pool[:10]:
            # 处理“代码块第一行是语言标签”的情况
            first_line, _, rest = cand.partition("\n")
            if first_line.strip().lower() in {"json", "javascript", "js"} and rest.strip():
                cand = rest.strip()
            try:
                return json.loads(cand)
            except Exception:
                continue

    preview = ""
    if isinstance(text, str):
        preview = text.strip().replace("\r\n", "\n")[:300]
    raise ValueError(f"JSON 解析失败。响应预览: {preview!r}")

