"""AI layer.

Everything that talks to a language model goes through AIService. The rest of the app never
calls Ollama (or any other provider) directly, and the model never touches the database.
"""
