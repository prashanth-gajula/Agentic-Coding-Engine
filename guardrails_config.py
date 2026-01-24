# guardrails_config.py

from guardrails import Guard
from guardrails.hub import DetectPII, ToxicLanguage
import logging

logger = logging.getLogger(__name__)

class GuardrailsManager:
    """Manages all guardrails for the agentic workflow"""
    
    def __init__(self):
        """Initialize guards"""
        
        # Input Guard - validates user input
        self.input_guard = Guard().use_many(
            DetectPII(
                pii_entities=[
                    "EMAIL_ADDRESS", 
                    "PHONE_NUMBER", 
                    "CREDIT_CARD",
                    "SSN",
                    "IP_ADDRESS"
                ],
                on_fail="exception"
            ),
            ToxicLanguage(
                threshold=0.5,
                validation_method="sentence",
                on_fail="exception"
            )
        )
        
        # Output Guard - validates agent output
        self.output_guard = Guard().use(
            DetectPII(
                pii_entities=[
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER", 
                    "CREDIT_CARD",
                    "SSN",
                    "API_KEY",
                    "PASSWORD"
                ],
                on_fail="fix"  # Redact PII in output instead of failing
            )
        )
    
    def validate_input(self, text: str) -> tuple[bool, str, str]:
        """
        Validate user input
        
        Returns:
            (is_valid, validated_text, error_message)
        """
        try:
            result = self.input_guard.validate(text)
            logger.info(f"✅ Input validation passed")
            return True, result.validated_output, ""
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"❌ Input validation failed: {error_msg}")
            return False, "", error_msg
    
    def validate_output(self, text: str) -> tuple[bool, str, str]:
        """
        Validate and sanitize agent output
        
        Returns:
            (is_valid, sanitized_text, error_message)
        """
        try:
            result = self.output_guard.validate(text)
            logger.info(f"✅ Output validation passed")
            return True, result.validated_output, ""
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"⚠️ Output sanitization issue: {error_msg}")
            # For output, we still return the text but log the issue
            return True, text, error_msg


# Global instance
guardrails_manager = GuardrailsManager()