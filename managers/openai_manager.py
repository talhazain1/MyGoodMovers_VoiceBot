import openai
import os
from dotenv import load_dotenv
import logging
import re
import json

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenAIManager:
    def __init__(self):
        # Set your OpenAI API key from the environment variables.
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("OPENAI_API_KEY not found in environment variables.")
            raise ValueError("OPENAI_API_KEY not found.")
        openai.api_key = self.api_key

    def extract_fields_from_text(self, system_prompt, user_text):
        """
        Calls OpenAI with a system prompt that instructs the model
        to output strictly valid JSON containing fields:
          origin, destination, move_size, move_date, additional_services, username, contact_no
        or null if missing.

        Returns a dictionary. It's up to the caller to handle parsing or further processing.
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # Change to "gpt-4" if available
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.2,  # Lower temperature for more deterministic output
                max_tokens=300,    # Increased tokens to accommodate all fields
                n=1,
                stop=None,
            )
            content = response["choices"][0]["message"]["content"].strip()
            logger.debug(f"OpenAI Extraction Response: {content}")
            # Attempt to parse JSON
            parsed_json = self._parse_json(content)
            return parsed_json
        except openai.Error as e:
            logger.error(f"OpenAI API Error during field extraction: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error during field extraction: {e}")
            return {}

    def get_general_response(self, system_content, user_content):
        """
        Fetch a response from OpenAI GPT for general queries using two separate inputs:
          1) system_content (instructions to keep answers short, brand context, etc.)
          2) user_content (the actual user prompt or combined conversation context).
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # Change to "gpt-4" if available
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=500,  # Increased tokens for more comprehensive responses
                temperature=0.7   # Higher temperature for conversational flexibility
            )
            # Extract and return the assistant's reply
            reply = response["choices"][0]["message"]["content"].strip()
            logger.debug(f"OpenAI General Response: {reply}")
            return reply
        except openai.AuthenticationError:
            logger.error("Invalid OpenAI API key.")
            return "Error: Invalid API key. Please check your OpenAI API key."
        except openai.BadRequestError as e:
            logger.error(f"OpenAI Bad Request: {e}")
            return f"Error: Bad request. Details: {e}"
        except openai.RateLimitError:
            logger.error("OpenAI Rate Limit Exceeded.")
            return "Error: Rate limit exceeded. Please try again later."
        except openai.APIError as e:
            logger.error(f"OpenAI API Error: {e}")
            return f"Error: OpenAI API error. Details: {e}"
        except Exception as e:
            logger.error(f"Unexpected error during general response: {e}")
            return f"An unexpected error occurred: {e}"

    def _parse_json(self, content):
        """
        Attempts to parse JSON from the OpenAI response.
        """
        try:
            # Clean the content if it contains markdown or other formatting
            if content.startswith("```") and content.endswith("```"):
                content = content[3:-3].strip()
            # Remove any trailing commas or syntax issues
            content = re.sub(r',\s*}', '}', content)
            parsed = json.loads(content)
            logger.debug(f"Parsed JSON: {parsed}")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error during JSON parsing: {e}")
            return {}
