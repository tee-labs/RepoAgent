from llama_index.llms.openai_like import OpenAILike

from repo_agent.doc_meta_info import DocItem
from repo_agent.log import logger
from repo_agent.prompt import chat_template
from repo_agent.settings import SettingsManager


class ChatEngine:
    """
    ChatEngine is used to generate the doc of functions or classes.
    """

    def __init__(self, project_manager):
        setting = SettingsManager.get_setting()

        self.llm = OpenAILike(
            api_key=setting.chat_completion.openai_api_key.get_secret_value(),
            api_base=setting.chat_completion.openai_base_url,
            timeout=setting.chat_completion.request_timeout,
            model=setting.chat_completion.model,
            temperature=setting.chat_completion.temperature,
            max_retries=1,
            is_chat_model=True,
        )
        # 某些 OpenAI 兼容 API 只支持 stream。为 True 时用 stream_chat 聚合结果。
        self.use_stream = setting.chat_completion.use_stream

    def build_prompt(self, doc_item: DocItem):
        """Builds and returns the system and user prompts based on the DocItem."""
        setting = SettingsManager.get_setting()

        code_info = doc_item.content
        referenced = len(doc_item.who_reference_me) > 0

        code_type = code_info["type"]
        code_name = code_info["name"]
        code_content = code_info["code_content"]
        have_return = code_info["have_return"]
        file_path = doc_item.get_full_name()

        def get_referenced_prompt(doc_item: DocItem) -> str:
            if len(doc_item.reference_who) == 0:
                return ""
            prompt = [
                """As you can see, the code calls the following objects, their code and docs are as following:"""
            ]
            for reference_item in doc_item.reference_who:
                instance_prompt = (
                    f"""obj: {reference_item.get_full_name()}\nDocument: \n{reference_item.md_content[-1] if len(reference_item.md_content) > 0 else 'None'}\nRaw code:```\n{reference_item.content['code_content'] if 'code_content' in reference_item.content.keys() else ''}\n```"""
                    + "=" * 10
                )
                prompt.append(instance_prompt)
            return "\n".join(prompt)

        def get_referencer_prompt(doc_item: DocItem) -> str:
            if len(doc_item.who_reference_me) == 0:
                return ""
            prompt = [
                """Also, the code has been called by the following objects, their code and docs are as following:"""
            ]
            for referencer_item in doc_item.who_reference_me:
                instance_prompt = (
                    f"""obj: {referencer_item.get_full_name()}\nDocument: \n{referencer_item.md_content[-1] if len(referencer_item.md_content) > 0 else 'None'}\nRaw code:```\n{referencer_item.content['code_content'] if 'code_content' in referencer_item.content.keys() else 'None'}\n```"""
                    + "=" * 10
                )
                prompt.append(instance_prompt)
            return "\n".join(prompt)

        def get_relationship_description(referencer_content, reference_letter):
            if referencer_content and reference_letter:
                return "And please include the reference relationship with its callers and callees in the project from a functional perspective"
            elif referencer_content:
                return "And please include the relationship with its callers in the project from a functional perspective."
            elif reference_letter:
                return "And please include the relationship with its callees in the project from a functional perspective."
            else:
                return ""

        code_type_tell = "Class" if code_type == "ClassDef" else "Function"
        parameters_or_attribute = (
            "attributes" if code_type == "ClassDef" else "parameters"
        )
        have_return_tell = (
            "**Output Example**: Mock up a possible appearance of the code's return value."
            if have_return
            else ""
        )
        combine_ref_situation = (
            "and combine it with its calling situation in the project,"
            if referenced
            else ""
        )

        referencer_content = get_referencer_prompt(doc_item)
        reference_letter = get_referenced_prompt(doc_item)
        has_relationship = get_relationship_description(
            referencer_content, reference_letter
        )

        project_structure_prefix = ", and the related hierarchical structure of this project is as follows (The current object is marked with an *):"

        return chat_template.format_messages(
            combine_ref_situation=combine_ref_situation,
            file_path=file_path,
            project_structure_prefix=project_structure_prefix,
            code_type_tell=code_type_tell,
            code_name=code_name,
            code_content=code_content,
            have_return_tell=have_return_tell,
            has_relationship=has_relationship,
            reference_letter=reference_letter,
            referencer_content=referencer_content,
            parameters_or_attribute=parameters_or_attribute,
            language=setting.project.language,
        )

    def generate_doc(self, doc_item: DocItem):
        """Generates documentation for a given DocItem."""
        messages = self.build_prompt(doc_item)

        try:
            if self.use_stream:
                return self._generate_doc_stream(messages)
            response = self.llm.chat(messages)
            self._log_token_usage(response)
            return response.message.content
        except Exception as e:
            logger.error(f"Error in llamaindex chat call: {e}")
            raise

    def _generate_doc_stream(self, messages):
        """stream 模式：聚合 stream_chat 的 chunks 取最终全文。

        每个 chunk 的 ``message.content`` 已是累积全文（llama_index OpenAI
        stream 实现内部累加），故取最后一个即可。usage 在 stream 下不保证
        可用——需服务端在末尾发 usage chunk 且请求带
        ``stream_options={"include_usage": True}``；取不到就跳过 token 日志。
        """
        last_response = None
        for chunk in self.llm.stream_chat(
            messages, stream_options={"include_usage": True}
        ):
            last_response = chunk
        final_text = (
            last_response.message.content if last_response is not None else ""
        )
        if last_response is not None:
            self._log_token_usage(last_response)
        return final_text

    @staticmethod
    def _log_token_usage(response):
        """记录 token 用量，容错：stream 下可能拿不到 usage。

        非 stream：response.raw.usage 有 prompt/completion/total_tokens。
        stream：usage 在最后一个 chunk 的 additional_kwargs（llama_index 解析后），
        或 raw.usage（取决于服务端）。任一拿不到都静默跳过该日志。
        """
        usage = getattr(response, "raw", None)
        usage = getattr(usage, "usage", None) if usage is not None else None
        if usage is None:
            # 回退到 additional_kwargs（stream 路径 llama_index 解析后存放处）
            ak = getattr(response, "additional_kwargs", {}) or {}
            if not ak:
                return
            prompt = ak.get("prompt_tokens")
            completion = ak.get("completion_tokens")
            total = ak.get("total_tokens")
            if prompt is None and completion is None:
                return
            logger.debug(f"LLM Prompt Tokens: {prompt}")
            logger.debug(f"LLM Completion Tokens: {completion}")
            logger.debug(f"Total LLM Token Count: {total}")
            return
        try:
            logger.debug(f"LLM Prompt Tokens: {usage.prompt_tokens}")
            logger.debug(f"LLM Completion Tokens: {usage.completion_tokens}")
            logger.debug(f"Total LLM Token Count: {usage.total_tokens}")
        except AttributeError:
            pass
