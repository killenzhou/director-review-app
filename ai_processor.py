# -*- coding: utf-8 -*-
import os
import json
import re
import google.generativeai as genai
from openai import OpenAI

# 绕过系统代理，防止连接本地 127.0.0.1 时报 502 Bad Gateway 错误
os.environ["NO_PROXY"] = "127.0.0.1,localhost"


OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "deepseek",
    "doubao",
    "openai-compatible",
    "lm-studio",
    "lmstudio",
    "llmstudio",
    "local-ai",
}
LOCAL_AI_PROVIDERS = {"lm-studio", "lmstudio", "llmstudio", "local-ai"}
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_LOCAL_MODEL = "Qwen3VL-8B-Instruct-Q4_K_M.gguf"


def extract_json(text):
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None

class AIProcessor:
    def __init__(self, provider, api_key, base_url, model_name):
        self.provider = provider
        self.model_name = model_name
        self.client = None
        
        try:
            if self.provider == "google-gemini":
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel(self.model_name or "gemini-2.5-flash")
            elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
                api_key = api_key or ("lm-studio" if self.provider in LOCAL_AI_PROVIDERS else None)
                base_url = self._normalize_base_url(base_url)
                self.model_name = self.model_name or (DEFAULT_LOCAL_MODEL if self.provider in LOCAL_AI_PROVIDERS else "")
                self.client = OpenAI(api_key=api_key, base_url=base_url)
            else:
                raise ValueError(f"不支持的服务商: {self.provider}")
        except Exception as e:
            raise ValueError(f"初始化AI客户端失败: {e}")

    def _normalize_base_url(self, base_url):
        base_url = (base_url or "").strip()
        if self.provider in LOCAL_AI_PROVIDERS:
            if not base_url or base_url == "N/A":
                base_url = DEFAULT_LOCAL_BASE_URL
            base_url = base_url.rstrip("/")
            if re.match(r"^https?://", base_url) and not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            return base_url
        return base_url or None

    def analyze(self, text, departments):
        """
        根据 provider 分派到具体的分析方法
        """
        if self.provider == "google-gemini":
            return self._analyze_gemini(text, departments)
        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            return self._analyze_openai_compatible(text, departments)
        else:
            return self._get_error_result(f"不支持的服务商: {self.provider}", text)

    def rewrite_review(self, text, departments):
        department_list_str = ", ".join([f"'{dep}'" for dep in departments])
        prompt = self._build_rewrite_prompt(text, department_list_str)
        if self.provider == "google-gemini":
            return self._run_gemini_prompt(prompt, departments)
        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            return self._run_openai_compatible_prompt(prompt, departments)
        return self._get_error_result(f"不支持的服务商: {self.provider}", text)

    def summarize_long_review(self, text, departments):
        department_list_str = ", ".join([f"'{dep}'" for dep in departments])
        if len(text) > 9000:
            chunk_results = []
            for i in range(0, len(text), 6000):
                chunk = text[i:i + 6000]
                prompt = self._build_long_video_chunk_prompt(chunk, department_list_str)
                if self.provider == "google-gemini":
                    result = self._run_gemini_prompt(prompt, departments)
                elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
                    result = self._run_openai_compatible_prompt(prompt, departments)
                else:
                    return self._get_error_result(f"不支持的服务商: {self.provider}", text)
                chunk_results.append(result.get("rewritten_review") or result.get("simplified_review", ""))
            text = "\n".join(item for item in chunk_results if item)
        prompt = self._build_long_video_prompt(text, department_list_str)
        if self.provider == "google-gemini":
            return self._run_gemini_prompt(prompt, departments)
        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            return self._run_openai_compatible_prompt(prompt, departments)
        return self._get_error_result(f"不支持的服务商: {self.provider}", text)

    def segment_long_video_discussions(self, timed_text, departments):
        department_list_str = ", ".join([f"'{dep}'" for dep in departments])
        chunks = self._split_timed_text_chunks(timed_text, max_chars=12000)
        all_segments = []
        for chunk in chunks:
            prompt = self._build_long_video_segmentation_prompt(chunk, department_list_str)
            if self.provider == "google-gemini":
                result = self._run_long_segments_gemini(prompt, departments)
            elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
                result = self._run_long_segments_openai(prompt, departments)
            else:
                return {"segments": []}
            all_segments.extend(result.get("segments", []))
        all_segments.sort(key=lambda item: float(item.get("start") or 0))
        return {"segments": all_segments}

    def _split_timed_text_chunks(self, timed_text, max_chars=12000):
        lines = str(timed_text or "").splitlines()
        chunks = []
        current = []
        current_len = 0
        for line in lines:
            line_len = len(line) + 1
            if current and current_len + line_len > max_chars:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len
        if current:
            chunks.append("\n".join(current))
        return chunks or [str(timed_text or "")]

    def _get_error_result(self, message, original_text=""):
        return {"simplified_review": f"AI分析失败: {message}", "keywords": [], "department": "错误"}

    def _analyze_gemini(self, text, departments):
        department_list_str = ", ".join([f"'{dep}'" for dep in departments])
        prompt = self._build_common_prompt(text, department_list_str)
        return self._run_gemini_prompt(prompt, departments)

    def _run_gemini_prompt(self, prompt, departments):
        response_text = ""
        
        try:
            generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
            response = self.client.generate_content(prompt, generation_config=generation_config)
            response_text = response.text
            result_dict = extract_json(response_text)
            if not result_dict: raise ValueError("AI返回的内容中未找到有效的JSON。")
            
            return self._normalize_result(result_dict, departments)
        except Exception as e:
            print(f"Gemini API分析时出错: {e}\n原始返回: {response_text[:200]}")
            return self._get_error_result(f"API错误: {e}")

    def _analyze_openai_compatible(self, text, departments):
        """
        为OpenAI, DeepSeek等兼容OpenAI API的服务商提供分析功能
        """
        department_list_str = ", ".join([f"'{dep}'" for dep in departments])
        prompt = self._build_common_prompt(text, department_list_str)
        return self._run_openai_compatible_prompt(prompt, departments)

    def _run_openai_compatible_prompt(self, prompt, departments):
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            result_str = response.choices[0].message.content
            result_dict = json.loads(result_str)
            return self._normalize_result(result_dict, departments)
        except Exception as e:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                result_str = response.choices[0].message.content
                result_dict = extract_json(result_str)
                if not result_dict:
                    raise ValueError("AI返回的内容中未找到有效的JSON。")
                return self._normalize_result(result_dict, departments)
            except Exception as retry_error:
                print(f"OpenAI兼容API分析时出错: {e}; 重试解析失败: {retry_error}")
                return self._get_error_result(f"API错误: {retry_error}")

    def _run_long_segments_openai(self, prompt, departments):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result_dict = json.loads(response.choices[0].message.content)
        except Exception as e:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                result_dict = extract_json(response.choices[0].message.content)
                if not result_dict:
                    raise ValueError("AI返回的内容中未找到有效的JSON。")
            except Exception as retry_error:
                print(f"长视频分段AI处理失败: {e}; 重试失败: {retry_error}")
                return {"segments": []}
        return self._normalize_long_segments(result_dict, departments)

    def _run_long_segments_gemini(self, prompt, departments):
        try:
            generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
            response = self.client.generate_content(prompt, generation_config=generation_config)
            result_dict = extract_json(response.text)
            if not result_dict:
                raise ValueError("AI返回的内容中未找到有效的JSON。")
            return self._normalize_long_segments(result_dict, departments)
        except Exception as e:
            print(f"Gemini 长视频分段失败: {e}")
            return {"segments": []}

    def _normalize_long_segments(self, result_dict, departments):
        if not isinstance(result_dict, dict):
            return {"segments": []}
        raw_segments = result_dict.get("issues", result_dict.get("segments", []))
        if not isinstance(raw_segments, list):
            return {"segments": []}
        normalized = []
        for item in raw_segments[:80]:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start", 0))
                end = float(item.get("end", 0))
            except (TypeError, ValueError):
                continue
            if end <= start:
                end = start + 8.0
            discussion = str(item.get("raw_discussion") or item.get("discussion") or item.get("full_review") or "").strip()
            meeting_note = str(item.get("meeting_note") or item.get("rewritten_review") or discussion).strip()
            simplified = str(item.get("simplified_review") or discussion).strip()
            keywords = item.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [part.strip() for part in re.split(r"[,，、\n]", keywords) if part.strip()]
            if not isinstance(keywords, list):
                keywords = []
            clean_keywords = []
            for keyword in keywords:
                keyword = str(keyword).strip()
                if keyword and keyword not in clean_keywords:
                    clean_keywords.append(keyword)
            raw_dept = str(item.get("department", "")).replace("，", ",")
            valid_depts = [d.strip() for d in raw_dept.split(",") if d.strip() in departments]
            department = ", ".join(valid_depts) if valid_depts else "未分类"
            if discussion or simplified:
                normalized.append({
                    "start": start,
                    "end": end,
                    "raw_discussion": discussion or simplified,
                    "discussion": discussion or simplified,
                    "meeting_note": meeting_note,
                    "simplified_review": simplified,
                    "keywords": clean_keywords[:5],
                    "department": department,
                    "confidence": item.get("confidence", ""),
                    "status": item.get("status", "AI生成"),
                })
        return {"segments": normalized}

    def _normalize_result(self, result_dict, departments):
        if not isinstance(result_dict, dict):
            return self._get_error_result("AI返回格式不是JSON对象")
        simplified = str(result_dict.get("simplified_review", "")).strip()
        keywords = result_dict.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [part.strip() for part in re.split(r"[,，、\n]", keywords) if part.strip()]
        if not isinstance(keywords, list):
            keywords = []
        raw_dept = str(result_dict.get("department", "")).replace("，", ",")
        valid_depts = [d.strip() for d in raw_dept.split(",") if d.strip() in departments]
        department = ", ".join(valid_depts) if valid_depts else "未分类"
        clean_keywords = []
        for item in keywords:
            item = str(item).strip()
            if item and item not in clean_keywords:
                clean_keywords.append(item)
        return {
            "simplified_review": simplified or "AI未能生成简化意见。",
            "keywords": clean_keywords[:5],
            "department": department,
            "rewritten_review": str(result_dict.get("rewritten_review", simplified or "")).strip()
        }

    def _build_common_prompt(self, text, department_list_str):
        return f"""
        你是影视动画审阅表整理助手。你的任务是把口语化审片意见压缩成准确、可执行的表格内容。

        必须遵守：
        - 只输出一个 JSON 对象，不要解释、前言、Markdown 或代码块。
        - JSON 只能包含 `simplified_review`, `keywords`, `department` 三个字段。
        - 只能使用原文明确提到的内容，或原文强烈暗示但没有歧义的内容。
        - 不要扩展、不要脑补、不要美化，不要添加原文没有的镜头对象、技术手段、原因、结果、参考镜头或部门。
        - 语音识别错字只在非常明确时纠正；不确定就保留原意或用“原文未说明具体对象”表达不确定性。

        字段要求：
        - `simplified_review`: 1 句简体中文，精准压缩核心修改意见，不增加新信息。
        - `keywords`: 2 到 5 个短词组，必须来自原文中的对象、问题或动作；内容少时可以少于 2 个。
        - `department`: 只能从 [{department_list_str}] 中选 1 个；无法判断时填“未分类”。

        示例：
        原文：“这个火别那么蓝，下面黑色拉丝多一点，后面罩子淡一点。”
        输出：
        {{
          "simplified_review": "火焰颜色不要偏蓝，底部增加黑色拉丝感，并淡化后方罩子。",
          "keywords": ["火焰偏蓝", "黑色拉丝", "罩子淡化"],
          "department": "UE特效, 合成"
        }}

        待处理原文：
        "{text}"
        """

    def _build_rewrite_prompt(self, text, department_list_str):
        return f"""
        你是影视动画审阅表整理助手。请把口语化审片反馈改写成可直接落表的修改意见。

        输出规则：
        - 只输出一个 JSON 对象，不要解释、注释、Markdown、代码块或多余文字。
        - JSON 必须且只能包含 `rewritten_review`, `simplified_review`, `keywords`, `department`。
        - `rewritten_review`: 1 到 2 句，专业、清楚、克制，只整理原文信息。
        - `simplified_review`: 1 句，精准简化核心修改意见。
        - `keywords`: 2 到 5 个短词组，只提取原文实际涉及的对象、问题、动作；内容少时可以少于 2 个。
        - `department`: 只能从 [{department_list_str}] 中选择 1 个；无法判断填“未分类”。

        严格限制：
        - 不要扩展、不要脑补、不要美化。
        - 不要添加原文没有的镜头对象、技术手段、制作原因、预期效果、参考镜头、情绪描述或部门归因。
        - 不要把一句模糊意见改成复杂方案；原文没说具体对象时，保留“不明确”。
        - 只修正非常明确的语音识别错字，例如“拉斯”可按上下文改为“拉丝”；不确定就不要改。
        - 关键词必须精准，不要使用“优化画面”“提升效果”“细节调整”这类空泛词。

        示例：
        原文：“这个火别那么蓝，下面黑色拉丝多一点，后面罩子淡一点。”
        输出：
        {{
          "rewritten_review": "火焰颜色不要偏蓝，底部增加黑色拉丝感；后方罩子需要淡化。",
          "simplified_review": "调整火焰偏蓝、黑色拉丝不足和后方罩子过强的问题。",
          "keywords": ["火焰偏蓝", "黑色拉丝", "罩子淡化"],
          "department": "UE特效, 合成"
        }}

        可用部门列表：
        [{department_list_str}]

        原始输入反馈：
        "{text}"
        """

    def _build_long_video_prompt(self, text, department_list_str):
        return f"""
        你是影视动画长视频反馈纪要整理助手。输入是一段较长的视频审阅转写文本，可能像会议纪要一样包含停顿、重复、闲聊和口语。

        输出规则：
        - 只输出一个 JSON 对象，不要解释、Markdown、代码块或多余文字。
        - JSON 必须且只能包含 `rewritten_review`, `simplified_review`, `keywords`, `department`。
        - `rewritten_review`: 写成长视频会议纲要，必须包含这些小标题：`会议主题`、`核心结论`、`主要问题`、`待办事项`。主要问题和待办事项用短条目表达。
        - `simplified_review`: 1 句总结这段长视频反馈的核心问题。
        - `keywords`: 3 到 5 个精准短词组，只来自原文实际涉及的对象、问题或动作。
        - `department`: 只能从 [{department_list_str}] 中选 1 个；跨部门或无法判断时填“未分类”。

        严格限制：
        - 不要扩展、不要脑补、不要添加原文没有的镜头对象、技术方案、原因、结果或参考。
        - 不要把闲聊内容写进纪要；只保留可执行反馈。
        - 如果原文没有明确问题，只写“原文未明确提出具体修改问题”，不要猜测。
        - 关键词不要用“整体优化”“细节调整”“提升效果”这类空泛词。
        - 可以汇总同类问题，但不能添加原文没有的制作要求。

        长视频转写文本：
        "{text}"
        """

    def _build_long_video_chunk_prompt(self, text, department_list_str):
        return f"""
        你是影视动画长视频反馈整理助手。下面是长视频转写文本的一段，请只提取这一段中明确出现的可执行修改问题。

        输出规则：
        - 只输出 JSON 对象，字段只能是 `rewritten_review`, `simplified_review`, `keywords`, `department`。
        - `rewritten_review`: 1 到 5 条短句，保留明确问题和修改方向。
        - `simplified_review`: 1 句概括本段重点。
        - `keywords`: 1 到 5 个精准短词组。
        - `department`: 只能从 [{department_list_str}] 中选 1 个；无法判断填“未分类”。
        - 不要扩展、不要脑补、不要添加原文没有的信息。
        - 如果本段没有明确问题，写“本段未明确提出具体修改问题”。

        转写片段：
        "{text}"
        """

    def _build_long_video_segmentation_prompt(self, timed_text, department_list_str):
        return f"""
        你是影视动画审片长视频分析助手。输入是带时间的完整转写文本，格式大致为 `[开始秒-结束秒] 文本`。

        任务：
        - 找出会议中所有围绕镜头制作、效果判断、方案选择、分工确认、参考要求、修改方向的讨论。
        - 每一个独立镜头、独立部门问题或独立待办输出一条 issue。
        - 不要求出现明确“修改”命令；只要讨论了制作问题、风险、取舍、分工或参考，就要记录。
        - 只过滤纯寒暄、无意义确认、完全无制作内容的闲聊。

        输出规则：
        - 只输出一个 JSON 对象，不要 Markdown、解释或代码块。
        - JSON 只能包含 `issues` 字段。
        - `issues` 是数组，每个元素包含：
          - `start`: 讨论开始秒数，数字。
          - `end`: 讨论结束秒数，数字。
          - `raw_discussion`: 这一段原始交流内容的精炼合并，但不能添加原文没有的信息。
          - `meeting_note`: 动画行业专业会议纪要式整理，说明问题、判断、方案或待办。
          - `simplified_review`: 1 句精准简化修改意见。
          - `keywords`: 1 到 5 个精准关键词。
          - `department`: 只能从 [{department_list_str}] 中选一个，无法判断填“未分类”。
          - `confidence`: high / medium / low。

        判断标准：
        - 有制作对象、部门、画面效果、镜头、方案、分工、参考、风险、待办之一，就应尽量记录。
        - 同一个镜头连续讨论同一问题，应合并成一条，start 取最早，end 取最晚。
        - 如果提到新镜头、新时间码、新对象或新问题，应拆成新条。
        - 不要脑补镜头号；镜头号和画面时间码会由程序截图 OCR 处理。

        带时间完整转写：
        {timed_text}
        """
