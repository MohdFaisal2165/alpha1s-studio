"""Gemini proposes a single allowlisted intent; no execution tools are exposed."""
import os
from .motions import validate_call

DECLARATION = {
    'name': 'propose_motion',
    'description': 'Propose a simulation preview. Use idle for unsupported requests.',
    'parameters': {'type': 'object', 'properties': {
        'motion': {'type': 'string', 'enum': ['idle', 'wave']}}, 'required': ['motion']},
}


def parse_calls(calls):
    if len(calls) != 1:
        raise ValueError('Exactly one function call required; nothing queued')
    c = calls[0]
    return validate_call(c.name, c.args)


def propose(text):
    if not text.strip() or len(text) > 2000:
        raise ValueError('Enter 1–2000 characters')
    model = os.environ.get('GEMINI_MODEL')
    key = os.environ.get('GEMINI_API_KEY')
    if not model or not key:
        raise ValueError('Set GEMINI_MODEL and GEMINI_API_KEY locally')
    from google import genai
    from google.genai import types
    with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=15000)) as client:
        response = client.models.generate_content(
            model=model, contents=text,
            config=types.GenerateContentConfig(
                system_instruction='Propose wave only for a greeting; otherwise idle. This is simulation.',
                tools=[types.Tool(function_declarations=[DECLARATION])],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                    mode='ANY', allowed_function_names=['propose_motion']))))
    return parse_calls(response.function_calls or [])
