from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    openai_api_key: Optional[str] = None  # we'll use this later

    # Model tiering: cheap/fast model for parsing, classification, categorization,
    # and the bounded verifier re-ask; a separate (currently identical) model for
    # the actual bullet-generation call, which is the one output candidates are
    # judged on. Raise openai_model_generate independently once a stronger tier
    # is chosen - kept configurable rather than hardcoded so no model ID is guessed.
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_generate: str = "gpt-4o-mini"

    # match_inferred_skills_to_jd runs on every tailor request (unconditional
    # semantic-credit pass) and needs to reliably catch subtler inferential
    # matches (e.g. Photoshop/Illustrator satisfying "Adobe CC") in a mixed
    # list of easy and hard requirements - verified gpt-4o-mini misses these
    # deterministically at temperature 0 while gpt-4.1-mini catches them
    # reliably, so this call gets its own tier rather than sharing
    # openai_model_fast with less accuracy-sensitive calls (domain
    # classification, inferred-skill suggestion).
    openai_model_matching: str = "gpt-4.1-mini"

    # classify_confirmed_skills and suggest_plausible_skills_grouped both
    # draw the same tool-vs-methodology boundary (e.g. "ETL Processes" is a
    # process, not a tool, even though it sounds technical). Compared three
    # tiers on this specific boundary: gpt-4o-mini gets it wrong consistently
    # (4/4 test runs, files it under Tools); gpt-5-mini gets it right
    # consistently (4/4) but as a reasoning model costs ~17x more and runs
    # ~21x slower per call (~1,470 hidden reasoning tokens on a simple
    # classification); gpt-4.1-mini never gets it wrong - it just omits the
    # term entirely rather than committing to a bucket (4/4) - at the same
    # latency/cost as gpt-4o-mini. Chosen deliberately: omitting an
    # ambiguous suggestion is an acceptable outcome (the picker already
    # treats "not suggested" as normal for anything not confidently
    # groundable), while filing it under the wrong bucket isn't - and
    # gpt-5-mini's cost/latency profile isn't worth it pipeline-adjacent
    # just to resolve rather than omit the rare ambiguous case.
    openai_model_classification: str = "gpt-4.1-mini"

    # Passed straight to AsyncOpenAI's built-in retry/backoff for transient
    # errors (rate limits, timeouts) - no separate retry library needed.
    openai_max_retries: int = 2

    model_config = {
        "env_file": ".env"
    }
    
    def validate_api_key(self):
        """Validate that the API key is set and not a placeholder."""
        if not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Please add your OpenAI API key to the .env file:\n"
                "OPENAI_API_KEY=your_actual_api_key_here\n"
                "Get your API key from: https://platform.openai.com/account/api-keys"
            )
        if self.openai_api_key in ["your_api_key_here", "your_actual_api_key_here", ""]:
            raise ValueError(
                "OPENAI_API_KEY is set to a placeholder value. Please replace it with your actual API key in the .env file.\n"
                "Get your API key from: https://platform.openai.com/account/api-keys"
            )
        if not self.openai_api_key.startswith("sk-"):
            raise ValueError(
                "OPENAI_API_KEY appears to be invalid. OpenAI API keys typically start with 'sk-'.\n"
                "Please check your API key in the .env file.\n"
                "Get your API key from: https://platform.openai.com/account/api-keys"
            )

settings = Settings()