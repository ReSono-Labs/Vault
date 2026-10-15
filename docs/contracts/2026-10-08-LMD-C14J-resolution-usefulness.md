# C14J — explicit resolution/usefulness review

NEW missing assessment dimensions; REUSE exact existing Vault
`app/vault_runtime/decision_learning/{reviewer,repository,rules}.py` and scoped
`memory/openai_reviewer.py` runner. Owner requires distinguishing successful,
correct-context handling from throwaway/unnecessary calls. No extra model call.

Decision CONTINUE: contract v3 requires request_resolution (resolved/corrected/
unresolved/unknown) and usefulness (necessary/helpful/unnecessary/harmful/unknown),
each with exact point-linked evidence/explanation. Model-derived resolved requires
final request, actual result AND captured final answer; usefulness needs request/
result. Captured corrected/unresolved cannot become successful via hindsight.
Changing proposals additionally require resolved and necessary/helpful, alongside
existing complete-source, correct tool/context/result, completed non-error execution,
capability and no-negative-feedback gates. Unknown capture remains analysis-only.
Old v2 checkpoints remain immutable, not upgraded/replayed as v3. Compiler version
advances; satisfaction still independently unknown without actual user feedback.
Official Structured Outputs documentation inspected October8: all fields required.

Counterexamples: correct but unnecessary lookup, useful result/wrong answer, unknown
outcome promoted from transport success, later repair excusing original failure,
unrelated citations. Synthetic tests prove validation not model accuracy. Internal
prebuild review CONTINUE bounded capability; source/publication/activation mounts
and actual semantic qualification remain separate requirements.
