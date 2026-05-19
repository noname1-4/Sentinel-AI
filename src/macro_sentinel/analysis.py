from __future__ import annotations

from macro_sentinel.llm_clients import BaseLLMClient
from macro_sentinel.models import AnalysisResult, AppConfig, Article


LANGUAGE_NAMES = {
    "vi": "Vietnamese",
    "en": "English",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
    "de": "German",
    "zh": "Chinese",
}

OUTPUT_LABELS = {
    "vi": ("T\u00f3m t\u1eaft", "Khuy\u1ebfn ngh\u1ecb"),
    "en": ("Summary", "Recommendation"),
    "fr": ("R\u00e9sum\u00e9", "Recommandation"),
    "it": ("Riepilogo", "Raccomandazione"),
    "es": ("Resumen", "Recomendaci\u00f3n"),
    "de": ("Zusammenfassung", "Empfehlung"),
    "zh": ("\u6458\u8981", "\u5efa\u8bae"),
}


class AnalysisEngine:
    def __init__(self, config: AppConfig, llm_client: BaseLLMClient) -> None:
        self.config = config
        self.llm_client = llm_client

    async def analyze(self, article: Article) -> AnalysisResult:
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(article)
        max_tokens = self._dynamic_max_tokens(article)
        markdown = await self.llm_client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=self.config.llm.temperature,
        )
        markdown = self._normalize_markdown(article, markdown)
        return AnalysisResult(
            article=article,
            markdown=markdown,
            language=self.config.language,
            provider=self.llm_client.provider,
            model=self.llm_client.model,
        )

    def _build_system_prompt(self) -> str:
        language_name = LANGUAGE_NAMES[self.config.language]
        summary_label, recommendation_label = OUTPUT_LABELS[self.config.language]
        return (
            "You are Macro-Sentinel, a concise real-time macroeconomic and crypto market analyst. "
            "Return only the final answer. Do not include chain-of-thought, prefaces, disclaimers, or extra sections. "
            f"Write entirely in {language_name}. Focus on liquidity, interest rates, inflation, central banks, "
            "growth, risk appetite, crypto flows, and market sentiment. "
            "The recommendation must include exactly one market regime label: Risk-On, Risk-Off, or Mixed. "
            "Use this exact Markdown structure and keep each labeled section to no more than 5 sentences:\n\n"
            "### [Title of Article]\n"
            f"**{summary_label} (Max 5 sentences):** [Concise summary focusing on liquidity, interest rates, "
            "macroeconomic impacts, or market sentiment]\n"
            f"**{recommendation_label} (Max 5 sentences):** [Actionable macro/swing trading insights. "
            "Identify Risk-On or Risk-Off status]\n"
        )

    def _build_user_prompt(self, article: Article) -> str:
        text = self._trim_article_text(article.text_for_analysis)
        published = article.published_at or "unknown"
        return (
            f"Source: {article.source_name}\n"
            f"Source category: {article.source_category}\n"
            f"Published: {published}\n"
            f"URL: {article.url}\n"
            f"Article Title: {article.title}\n\n"
            "Article Text or Description:\n"
            f"{text}"
        )

    def _trim_article_text(self, text: str) -> str:
        clean = " ".join((text or "").split())
        max_chars = max(500, self.config.fetch.max_article_chars)
        if len(clean) <= max_chars:
            return clean
        trimmed = clean[:max_chars].rsplit(" ", 1)[0]
        return f"{trimmed}..."

    def _dynamic_max_tokens(self, article: Article) -> int:
        min_tokens = self.config.llm.min_output_tokens
        max_tokens = self.config.llm.max_output_tokens
        input_chars = len(article.title) + len(article.text_for_analysis)
        calculated = min_tokens + min(250, input_chars // 120)
        return max(min_tokens, min(max_tokens, calculated))

    def _normalize_markdown(self, article: Article, markdown: str) -> str:
        clean = markdown.strip()
        if not clean.startswith("### "):
            return f"### {article.title}\n{clean}"
        return clean
