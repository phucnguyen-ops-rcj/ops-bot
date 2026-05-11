client<llm> OpsExtractor {
  provider "openai"
  options {
    model "gpt-5-mini"
    api_key env.OPENAI_API_KEY
  }
}

generator python_client {
  output_type "python/pydantic"
  output_dir "../src"
  version "0.222.0"
}
