## Instructions for Extracting Final Scores

**Objective:** Given an response of an evaluation prompt, extract the final score presented within the response and format it specifically.

**Process:**
1. **Analyze the response:** Scan the response to identify the final score provided by the evaluator.
2. **Extract and format the final answer:** Present the extracted score on a new line, preceded exactly by "Final answer: ".

**Formatting Rules:**
* **Evaluation Categories:** The expected output must be one of the following categories: ‘correct‘, ‘partial‘, ‘almost‘, ‘incorrect‘, or ‘not found‘.
* **Score Identification:** The extraction is based on identifying the keyword used by the evaluator to summarize their conclusion. The criteria associated with these keywords are:
  * **incorrect:** The evaluator concluded that the solution is completely incorrect or irrelevant.
  * **partial:** The evaluator concluded that the solution is partially correct but has significant errors or omissions.
  * **almost:** The evaluator concluded that the solution is almost correct but contains minor errors or inaccuracies.
  * **correct:** The evaluator concluded that the solution is fully correct and complete.
  * **not_found:** The evaluation response does not clearly contain one of the four explicit scores listed above.
* **Extraction:** Determine the provided score from the response and extract the category (‘correct‘, ‘partial‘, ‘almost‘, or ‘incorrect‘). If a score cannot be reliably identified within the text, the output must be ‘not_found‘.

**Note:** No additional markings or explanations are needed beyond "Final answer: " and the extracted answer.

Below is the response:
{Model Response}
