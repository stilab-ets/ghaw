# Saved Model Experiments

Run from the repository root:

```bash
python rq4/calculate_rq4_agreement.py
```

`predictions/<model>/<k>shot.json` stores each file's parsed response, evidence
lines, source hash, and generation settings. Model folders correspond to
Gemini 3.1 Pro Preview (`gemini-3.1-pro-preview`), GLM-5.2
(`zai-org/glm-5.2-maas`), and GPT-OSS-120B (`openai/gpt-oss-120b-maas`).
The shot settings are zero, one, three, and five positive snippets per label,
not that many complete labeled documents.

## Prompts

- `prompts/system_prompt.txt`: exact base system prompt and taxonomy definitions.
- `prompts/<k>shot_messages.json`: exact system and user text for each target,
  shared across the models. Bodies include their original source line numbers.
- `prompts/example_pool.json`: frozen candidate snippets.
- `prompts/<k>shot_demonstrations.json`: the selected snippets for each target.
- `prompts/template.md`: compact presentation of the common labeling task.

The schema and API transport differ by provider. The actual task messages,
definitions, exclusions, example selections, and target bodies are shared.
The package preserves the used snippets rather than selecting new examples
during evaluation. No cloud generation or authentication scripts are included.

## Settings

Temperature is zero. Gemini uses high reasoning and GLM uses enabled reasoning.
GPT-OSS uses the successful saved responses from the original and recovery runs.
Its output limits vary between 16,384, 32,768, and 65,536 tokens. Some recovery
responses use medium reasoning instead of high. The actual limit and reasoning
setting are recorded per prediction. These saved results must not be described
as coming from one uniform GPT generation budget or reasoning setting.

## Outputs

`output/comparison.csv` retains full numerical precision. `output/paper_table.md`
formats the same values for the manuscript. Model-specific output folders contain
per-label confusion counts and per-file disagreements. All reference labels come
from `data/rq3_sample/labels/resolved.json`.
