client<llm> OpsExtractor {
  provider "openai"
  options {
    model "gpt-5-mini"
  }
}

generator python_client {
  output_type "python/pydantic"
  output_dir "../src"
  version "0.222.0"
}
