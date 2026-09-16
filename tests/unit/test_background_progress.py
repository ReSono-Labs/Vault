from app.vault_runtime.background_agent.contracts import BackgroundRunState, ExecutionRecipe
from app.vault_runtime.background_agent.progress import project_progress


def test_project_progress_matches_r1_working_label() -> None:
    progress = project_progress(BackgroundRunState.RUNNING, ExecutionRecipe.SELF_REVIEW, ())
    assert progress.label == "Working and checking the result"
    assert progress.tone == "active"
    assert progress.fraction == 0.52
    assert progress.active is True
