# Recommended Models

A list of generally strong up-to-date models on openrouter for a range of options. This list is not exhaustive, but it is a decent starting point.

**Note:** this list has small models, but none that are suitable for a huggingface download to run local experiments (at least on an A100). Those would need to be much smaller.

Fixed model list for CLI selection, enriched with metadata from OpenRouter.

| Model ID | Provider | Bucket | Context | Prompt | Completion | Created |
|---|---|---|---:|---:|---:|---:|
| `google/gemini-3-flash-preview` | google | fast | 1048576 | $0.0000005 | $0.000003 | 2025-12-17 |
| `google/gemini-3.1-pro-preview` | google | frontier | 1048576 | $0.000002 | $0.000012 | 2026-02-19 |
| `google/gemini-3.1-flash-lite-preview` | google | small | 1048576 | $0.00000025 | $0.0000015 | 2026-03-03 |
| `google/gemini-3-pro-image-preview` | google | multimodal | 65536 | $0.000002 | $0.000012 | 2025-11-20 |
| `google/gemini-3.1-flash-image-preview` | google | multimodal | 65536 | $0.0000005 | $0.000003 | 2026-02-26 |
| `google/gemma-2-27b-it` | google | general | 8192 | $0.00000065 | $0.00000065 | 2024-07-13 |
| `anthropic/claude-opus-4.6` | anthropic | frontier | 1000000 | $0.000005 | $0.000025 | 2026-02-04 |
| `anthropic/claude-sonnet-4.6` | anthropic | general | 1000000 | $0.000003 | $0.000015 | 2026-02-17 |
| `qwen/qwen3.5-27b` | qwen | general | 262144 | $0.0000002 | $0.00000156 | 2026-02-25 |
| `qwen/qwen3.5-35b-a3b` | qwen | general | 262144 | $0.00000016 | $0.0000013 | 2026-02-25 |
| `qwen/qwen3.5-plus-02-15` | qwen | general | 1000000 | $0.00000026 | $0.00000156 | 2026-02-16 |
| `qwen/qwen3-max-thinking` | qwen | frontier | 262144 | $0.00000078 | $0.0000039 | 2026-02-09 |
| `openai/gpt-oss-120b` | openai | frontier | 131072 | $0.00000004 | $0.00000019 | 2025-08-05 |
| `openai/gpt-oss-20b:nitro` | openai | general | unknown | unknown | unknown | unknown |
| `nvidia/llama-3.3-nemotron-super-49b-v1.5` | nvidia | general | 131072 | $0.0000001 | $0.0000004 | 2025-10-10 |
| `nvidia/nemotron-3-nano-30b-a3b` | nvidia | small | 262144 | $0.00000005 | $0.0000002 | 2025-12-14 |
| `deepseek/deepseek-v3.2-speciale` | deepseek | general | 163840 | $0.0000004 | $0.0000012 | 2025-12-01 |
| `z-ai/glm-5` | z-ai | general | 202752 | $0.0000008 | $0.00000256 | 2026-02-11 |
| `moonshotai/kimi-k2.5` | moonshotai | general | 262144 | $0.00000045 | $0.0000022 | 2026-01-27 |


**STOP HERE** to prevent pollution of model context.
---

## Details

### `google/gemini-3-flash-preview`

- **Name:** Google: Gemini 3 Flash Preview
- **Provider:** google
- **Bucket:** fast
- **Context length:** 1048576
- **Prompt price:** $0.0000005
- **Completion price:** $0.000003
- **Created:** 2025-12-17
- **Modality:** text+image+file+audio+video->text
- **Input modalities:** text, image, file, audio, video
- **Output modalities:** text
- **Tokenizer:** Gemini
- **Instruct type:** —
- **Description:** Gemini 3 Flash Preview is a high speed, high value thinking model designed for agentic workflows, multi turn chat, and coding assistance. It delivers near Pro level reasoning and tool use performance with substantially lower latency than larger Gemini variants, making it well suited for interactive development, long running agent loops, and collaborative coding tasks. Compared to Gemini 2.5 Flash, it provides broad quality improvements across reasoning, multimodal understanding, and reliability.

The model supports a 1M token context window and multimodal inputs including text, images, audio, video, and PDFs, with text output. It includes configurable reasoning via thinking levels (minimal, low, medium, high), structured output, tool use, and automatic context caching. Gemini 3 Flash Preview is optimized for users who want strong reasoning and agentic behavior without the cost or latency of full scale frontier models.

### `google/gemini-3.1-pro-preview`

- **Name:** Google: Gemini 3.1 Pro Preview
- **Provider:** google
- **Bucket:** frontier
- **Context length:** 1048576
- **Prompt price:** $0.000002
- **Completion price:** $0.000012
- **Created:** 2026-02-19
- **Modality:** text+image+file+audio+video->text
- **Input modalities:** audio, file, image, text, video
- **Output modalities:** text
- **Tokenizer:** Gemini
- **Instruct type:** —
- **Description:** Gemini 3.1 Pro Preview is Google’s frontier reasoning model, delivering enhanced software engineering performance, improved agentic reliability, and more efficient token usage across complex workflows. Building on the multimodal foundation of the Gemini 3 series, it combines high-precision reasoning across text, image, video, audio, and code with a 1M-token context window. Reasoning Details must be preserved when using multi-turn tool calling, see our docs here: https://openrouter.ai/docs/use-cases/reasoning-tokens#preserving-reasoning. The 3.1 update introduces measurable gains in SWE benchmarks and real-world coding environments, along with stronger autonomous task execution in structured domains such as finance and spreadsheet-based workflows.

Designed for advanced development and agentic systems, Gemini 3.1 Pro Preview improves long-horizon stability and tool orchestration while increasing token efficiency. It introduces a new medium thinking level to better balance cost, speed, and performance. The model excels in agentic coding, structured planning, multimodal analysis, and workflow automation, making it well-suited for autonomous agents, financial modeling, spreadsheet automation, and high-context enterprise tasks.

### `google/gemini-3.1-flash-lite-preview`

- **Name:** Google: Gemini 3.1 Flash Lite Preview
- **Provider:** google
- **Bucket:** small
- **Context length:** 1048576
- **Prompt price:** $0.00000025
- **Completion price:** $0.0000015
- **Created:** 2026-03-03
- **Modality:** text+image+file+audio+video->text
- **Input modalities:** text, image, video, file, audio
- **Output modalities:** text
- **Tokenizer:** Gemini
- **Instruct type:** —
- **Description:** Gemini 3.1 Flash Lite Preview is Google's high-efficiency model optimized for high-volume use cases. It outperforms Gemini 2.5 Flash Lite on overall quality and approaches Gemini 2.5 Flash performance across key capabilities. Improvements span audio input/ASR, RAG snippet ranking, translation, data extraction, and code completion. Supports full thinking levels (minimal, low, medium, high) for fine-grained cost/performance trade-offs. Priced at half the cost of Gemini 3 Flash.

### `google/gemini-3-pro-image-preview`

- **Name:** Google: Nano Banana Pro (Gemini 3 Pro Image Preview)
- **Provider:** google
- **Bucket:** multimodal
- **Context length:** 65536
- **Prompt price:** $0.000002
- **Completion price:** $0.000012
- **Created:** 2025-11-20
- **Modality:** text+image->text+image
- **Input modalities:** image, text
- **Output modalities:** image, text
- **Tokenizer:** Gemini
- **Instruct type:** —
- **Description:** Nano Banana Pro is Google’s most advanced image-generation and editing model, built on Gemini 3 Pro. It extends the original Nano Banana with significantly improved multimodal reasoning, real-world grounding, and high-fidelity visual synthesis. The model generates context-rich graphics, from infographics and diagrams to cinematic composites, and can incorporate real-time information via Search grounding.

It offers industry-leading text rendering in images (including long passages and multilingual layouts), consistent multi-image blending, and accurate identity preservation across up to five subjects. Nano Banana Pro adds fine-grained creative controls such as localized edits, lighting and focus adjustments, camera transformations, and support for 2K/4K outputs and flexible aspect ratios. It is designed for professional-grade design, product visualization, storyboarding, and complex multi-element compositions while remaining efficient for general image creation workflows.

### `google/gemini-3.1-flash-image-preview`

- **Name:** Google: Nano Banana 2 (Gemini 3.1 Flash Image Preview)
- **Provider:** google
- **Bucket:** multimodal
- **Context length:** 65536
- **Prompt price:** $0.0000005
- **Completion price:** $0.000003
- **Created:** 2026-02-26
- **Modality:** text+image->text+image
- **Input modalities:** image, text
- **Output modalities:** image, text
- **Tokenizer:** Gemini
- **Instruct type:** —
- **Description:** Gemini 3.1 Flash Image Preview, a.k.a. "Nano Banana 2," is Google’s latest state of the art image generation and editing model, delivering Pro-level visual quality at Flash speed. It combines advanced contextual understanding with fast, cost-efficient inference, making complex image generation and iterative edits significantly more accessible. Aspect ratios can be controlled with the [image_config API Parameter](https://openrouter.ai/docs/features/multimodal/image-generation#image-aspect-ratio-configuration)

### `google/gemma-2-27b-it`

- **Name:** Google: Gemma 2 27B
- **Provider:** google
- **Bucket:** general
- **Context length:** 8192
- **Prompt price:** $0.00000065
- **Completion price:** $0.00000065
- **Created:** 2024-07-13
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** Gemini
- **Instruct type:** gemma
- **Description:** Gemma 2 27B by Google is an open model built from the same research and technology used to create the [Gemini models](/models?q=gemini).

Gemma models are well-suited for a variety of text generation tasks, including question answering, summarization, and reasoning.

See the [launch announcement](https://blog.google/technology/developers/google-gemma-2/) for more details. Usage of Gemma is subject to Google's [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

### `anthropic/claude-opus-4.6`

- **Name:** Anthropic: Claude Opus 4.6
- **Provider:** anthropic
- **Bucket:** frontier
- **Context length:** 1000000
- **Prompt price:** $0.000005
- **Completion price:** $0.000025
- **Created:** 2026-02-04
- **Modality:** text+image->text
- **Input modalities:** text, image
- **Output modalities:** text
- **Tokenizer:** Claude
- **Instruct type:** —
- **Description:** Opus 4.6 is Anthropic’s strongest model for coding and long-running professional tasks. It is built for agents that operate across entire workflows rather than single prompts, making it especially effective for large codebases, complex refactors, and multi-step debugging that unfolds over time. The model shows deeper contextual understanding, stronger problem decomposition, and greater reliability on hard engineering tasks than prior generations.

Beyond coding, Opus 4.6 excels at sustained knowledge work. It produces near-production-ready documents, plans, and analyses in a single pass, and maintains coherence across very long outputs and extended sessions. This makes it a strong default for tasks that require persistence, judgment, and follow-through, such as technical design, migration planning, and end-to-end project execution.

For users upgrading from earlier Opus versions, see our [official migration guide here](https://openrouter.ai/docs/guides/guides/model-migrations/claude-4-6-opus)

### `anthropic/claude-sonnet-4.6`

- **Name:** Anthropic: Claude Sonnet 4.6
- **Provider:** anthropic
- **Bucket:** general
- **Context length:** 1000000
- **Prompt price:** $0.000003
- **Completion price:** $0.000015
- **Created:** 2026-02-17
- **Modality:** text+image->text
- **Input modalities:** text, image
- **Output modalities:** text
- **Tokenizer:** Claude
- **Instruct type:** —
- **Description:** Sonnet 4.6 is Anthropic's most capable Sonnet-class model yet, with frontier performance across coding, agents, and professional work. It excels at iterative development, complex codebase navigation, end-to-end project management with memory, polished document creation, and confident computer use for web QA and workflow automation.

### `qwen/qwen3.5-27b`

- **Name:** Qwen: Qwen3.5-27B
- **Provider:** qwen
- **Bucket:** general
- **Context length:** 262144
- **Prompt price:** $0.0000002
- **Completion price:** $0.00000156
- **Created:** 2026-02-25
- **Modality:** text+image+video->text
- **Input modalities:** text, image, video
- **Output modalities:** text
- **Tokenizer:** Qwen3
- **Instruct type:** —
- **Description:** The Qwen3.5 27B native vision-language Dense model incorporates a linear attention mechanism, delivering fast response times while balancing inference speed and performance. Its overall capabilities are comparable to those of the Qwen3.5-122B-A10B.

### `qwen/qwen3.5-35b-a3b`

- **Name:** Qwen: Qwen3.5-35B-A3B
- **Provider:** qwen
- **Bucket:** general
- **Context length:** 262144
- **Prompt price:** $0.00000016
- **Completion price:** $0.0000013
- **Created:** 2026-02-25
- **Modality:** text+image+video->text
- **Input modalities:** text, image, video
- **Output modalities:** text
- **Tokenizer:** Qwen3
- **Instruct type:** —
- **Description:** The Qwen3.5 Series 35B-A3B is a native vision-language model designed with a hybrid architecture that integrates linear attention mechanisms and a sparse mixture-of-experts model, achieving higher inference efficiency. Its overall performance is comparable to that of the Qwen3.5-27B.

### `qwen/qwen3.5-plus-02-15`

- **Name:** Qwen: Qwen3.5 Plus 2026-02-15
- **Provider:** qwen
- **Bucket:** general
- **Context length:** 1000000
- **Prompt price:** $0.00000026
- **Completion price:** $0.00000156
- **Created:** 2026-02-16
- **Modality:** text+image+video->text
- **Input modalities:** text, image, video
- **Output modalities:** text
- **Tokenizer:** Qwen3
- **Instruct type:** —
- **Description:** The Qwen3.5 native vision-language series Plus models are built on a hybrid architecture that integrates linear attention mechanisms with sparse mixture-of-experts models, achieving higher inference efficiency. In a variety of task evaluations, the 3.5 series consistently demonstrates performance on par with state-of-the-art leading models. Compared to the 3 series, these models show a leap forward in both pure-text and multimodal capabilities.

### `qwen/qwen3-max-thinking`

- **Name:** Qwen: Qwen3 Max Thinking
- **Provider:** qwen
- **Bucket:** frontier
- **Context length:** 262144
- **Prompt price:** $0.00000078
- **Completion price:** $0.0000039
- **Created:** 2026-02-09
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** Qwen
- **Instruct type:** —
- **Description:** Qwen3-Max-Thinking is the flagship reasoning model in the Qwen3 series, designed for high-stakes cognitive tasks that require deep, multi-step reasoning. By significantly scaling model capacity and reinforcement learning compute, it delivers major gains in factual accuracy, complex reasoning, instruction following, alignment with human preferences, and agentic behavior.

### `openai/gpt-oss-120b`

- **Name:** OpenAI: gpt-oss-120b
- **Provider:** openai
- **Bucket:** frontier
- **Context length:** 131072
- **Prompt price:** $0.00000004
- **Completion price:** $0.00000019
- **Created:** 2025-08-05
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** GPT
- **Instruct type:** —
- **Description:** gpt-oss-120b is an open-weight, 117B-parameter Mixture-of-Experts (MoE) language model from OpenAI designed for high-reasoning, agentic, and general-purpose production use cases. It activates 5.1B parameters per forward pass and is optimized to run on a single H100 GPU with native MXFP4 quantization. The model supports configurable reasoning depth, full chain-of-thought access, and native tool use, including function calling, browsing, and structured output generation.

### `openai/gpt-oss-20b:nitro`

- **Name:** openai/gpt-oss-20b:nitro
- **Provider:** openai
- **Bucket:** general
- **Context length:** unknown
- **Prompt price:** unknown
- **Completion price:** unknown
- **Created:** unknown
- **Modality:** unknown
- **Input modalities:** —
- **Output modalities:** —
- **Tokenizer:** —
- **Instruct type:** —
- **Description:** Model not found in API response.

### `nvidia/llama-3.3-nemotron-super-49b-v1.5`

- **Name:** NVIDIA: Llama 3.3 Nemotron Super 49B V1.5
- **Provider:** nvidia
- **Bucket:** general
- **Context length:** 131072
- **Prompt price:** $0.0000001
- **Completion price:** $0.0000004
- **Created:** 2025-10-10
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** Llama3
- **Instruct type:** —
- **Description:** Llama-3.3-Nemotron-Super-49B-v1.5 is a 49B-parameter, English-centric reasoning/chat model derived from Meta’s Llama-3.3-70B-Instruct with a 128K context. It’s post-trained for agentic workflows (RAG, tool calling) via SFT across math, code, science, and multi-turn chat, followed by multiple RL stages; Reward-aware Preference Optimization (RPO) for alignment, RL with Verifiable Rewards (RLVR) for step-wise reasoning, and iterative DPO to refine tool-use behavior. A distillation-driven Neural Architecture Search (“Puzzle”) replaces some attention blocks and varies FFN widths to shrink memory footprint and improve throughput, enabling single-GPU (H100/H200) deployment while preserving instruction following and CoT quality.

In internal evaluations (NeMo-Skills, up to 16 runs, temp = 0.6, top_p = 0.95), the model reports strong reasoning/coding results, e.g., MATH500 pass@1 = 97.4, AIME-2024 = 87.5, AIME-2025 = 82.71, GPQA = 71.97, LiveCodeBench (24.10–25.02) = 73.58, and MMLU-Pro (CoT) = 79.53. The model targets practical inference efficiency (high tokens/s, reduced VRAM) with Transformers/vLLM support and explicit “reasoning on/off” modes (chat-first defaults, greedy recommended when disabled). Suitable for building agents, assistants, and long-context retrieval systems where balanced accuracy-to-cost and reliable tool use matter.

### `nvidia/nemotron-3-nano-30b-a3b`

- **Name:** NVIDIA: Nemotron 3 Nano 30B A3B
- **Provider:** nvidia
- **Bucket:** small
- **Context length:** 262144
- **Prompt price:** $0.00000005
- **Completion price:** $0.0000002
- **Created:** 2025-12-14
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** Other
- **Instruct type:** —
- **Description:** NVIDIA Nemotron 3 Nano 30B A3B is a small language MoE model with highest compute efficiency and accuracy for developers to build specialized agentic AI systems.

The model is fully open with open-weights, datasets and recipes so developers can easily
customize, optimize, and deploy the model on their infrastructure for maximum privacy and
security.

### `deepseek/deepseek-v3.2-speciale`

- **Name:** DeepSeek: DeepSeek V3.2 Speciale
- **Provider:** deepseek
- **Bucket:** general
- **Context length:** 163840
- **Prompt price:** $0.0000004
- **Completion price:** $0.0000012
- **Created:** 2025-12-01
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** DeepSeek
- **Instruct type:** —
- **Description:** DeepSeek-V3.2-Speciale is a high-compute variant of DeepSeek-V3.2 optimized for maximum reasoning and agentic performance. It builds on DeepSeek Sparse Attention (DSA) for efficient long-context processing, then scales post-training reinforcement learning to push capability beyond the base model. Reported evaluations place Speciale ahead of GPT-5 on difficult reasoning workloads, with proficiency comparable to Gemini-3.0-Pro, while retaining strong coding and tool-use reliability. Like V3.2, it benefits from a large-scale agentic task synthesis pipeline that improves compliance and generalization in interactive environments.

### `z-ai/glm-5`

- **Name:** Z.ai: GLM 5
- **Provider:** z-ai
- **Bucket:** general
- **Context length:** 202752
- **Prompt price:** $0.0000008
- **Completion price:** $0.00000256
- **Created:** 2026-02-11
- **Modality:** text->text
- **Input modalities:** text
- **Output modalities:** text
- **Tokenizer:** Other
- **Instruct type:** —
- **Description:** GLM-5 is Z.ai’s flagship open-source foundation model engineered for complex systems design and long-horizon agent workflows. Built for expert developers, it delivers production-grade performance on large-scale programming tasks, rivaling leading closed-source models. With advanced agentic planning, deep backend reasoning, and iterative self-correction, GLM-5 moves beyond code generation to full-system construction and autonomous execution.

### `moonshotai/kimi-k2.5`

- **Name:** MoonshotAI: Kimi K2.5
- **Provider:** moonshotai
- **Bucket:** general
- **Context length:** 262144
- **Prompt price:** $0.00000045
- **Completion price:** $0.0000022
- **Created:** 2026-01-27
- **Modality:** text+image->text
- **Input modalities:** text, image
- **Output modalities:** text
- **Tokenizer:** Other
- **Instruct type:** —
- **Description:** Kimi K2.5 is Moonshot AI's native multimodal model, delivering state-of-the-art visual coding capability and a self-directed agent swarm paradigm. Built on Kimi K2 with continued pretraining over approximately 15T mixed visual and text tokens, it delivers strong performance in general reasoning, visual coding, and agentic tool-calling.

Total models: **19**
