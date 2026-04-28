# PawPal+ Project Reflection


**Limitations and biases**

The system has several limitations worth naming honestly:

- **Narrow knowledge base.** The RAG corpus covers 18 chunks across four species (dogs, cats, rabbits, birds). For anything outside that set — reptiles, fish, hamsters. The model gets no retrieved context and falls back on whatever Llama 3.3 absorbed in training, which may be inaccurate or outdated.
- **Tag-overlap retrieval is literal.** A dog described as having "mobility difficulty" surfaces the arthritis entries less strongly than one described with the exact word "arthritis." The system rewards owners who already know the clinical vocabulary, the opposite of who needs the most guidance.
- **Breed and regional bias.** Llama 3.3 likely has far deeper training data on popular Western breeds (Labrador, Golden Retriever, Poodle) than on uncommon ones. Exercise and grooming advice may be less accurate for less-represented breeds. The knowledge base also assumes heartworm prevention is needed year-round, which is not true in all climates.
- **No individual medical history.** Two eight-year-old Labradors with completely different health histories receive the same "senior dog" guidelines. The system has no way to weigh a specific animal's diagnosed conditions against generic lifecycle advice.

**Misuse potential and prevention**

The most realistic misuse is an owner treating AI-generated task suggestions as a substitute for veterinary advice especially for a sick or newly-diagnosed pet. A user who enters "kidney disease" in the health notes field might trust the returned task list as a complete care protocol, when the medication timing and dietary details should come from a vet, not an LLM prompted with an 18-chunk knowledge base.

A subtler risk is prompt injection through the health notes field: a user could enter text designed to override the system prompt and elicit arbitrary output from the model.

*Preventions already in place:*
- Retrieved knowledge-base chunks are shown in the UI under an expander ("What the AI saw"), so the user can trace every suggestion back to its source.
- Forcing `tool_choice="required"` with a strict JSON schema prevents the model from producing free-form text, which limits the blast radius of prompt injection — the output must conform to the schema regardless of what the prompt said.

*Preventions that should be added:*
- A visible disclaimer that suggestions are not veterinary advice and should be reviewed with a vet for sick or medicated animals.
- Input sanitization on the health notes field to strip injection patterns before they reach the model.

**c. Surprises during reliability testing**

The most surprising result came from a test I expected to be trivially true: asserting that an unknown species ("fish") would return an empty list from `retrieve_guidelines`. It failed. The reason was non-obvious: "fish" with age 1.0 maps to the lifecycle label "adult," and "adult" is a tag in `dog_exercise_adult`. So the retrieval returns dog exercise docs for a fish not because the species matched, but because the lifecycle stage did. There is no species gate; any positive score qualifies an entry for inclusion.

This is a real reliability gap: an owner who accidentally selects the wrong species would receive confident-sounding but completely irrelevant guidelines, and the system would give no warning. The test was updated to document this behavior rather than hide it behind a forced assertion, and it surfaced a concrete improvement adding a minimum-score threshold that requires at least a species or lifecycle match, not just any tag overlap.

**d. AI collaboration**

Claude Code was used from time to time for this project for design feedback, debugging, writing boilerplate, and explaining unfamiliar APIs (especially the Groq function-calling format).

*One instance where the AI gave a helpful suggestion:* When implementing confidence scoring, Claude proposed structuring the function as four independent multiplicative penalties like RAG coverage, warnings, extra iterations, and budget overrun rather than a single additive score. The multiplicative structure was the right call: it means compounding problems compound the penalty too. A result with two warnings and a budget overrun scores far lower than either issue alone, which correctly reflects that both failing at once is worse than either in isolation. I wouldn't have landed on that design without the suggestion.

*One instance where the suggestion was flawed:* When writing the test for unknown-species retrieval, Claude initially wrote `assert docs == []`, reasoning that "fish" has no entries in the knowledge base and should therefore return nothing. That test failed because Claude did not trace through the actual scoring logic specifically that lifecycle tags like "adult" are shared across all species entries and still fire even when the species tag misses. The fix required understanding the retrieval internals myself and rewriting the test to document the real behavior instead of the assumed one. This was a concrete reminder that AI-generated tests can be confidently wrong: the assertion looked reasonable on the surface but was built on an incorrect assumption about how the function worked internally. 
