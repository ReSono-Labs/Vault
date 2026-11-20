"""vault.work must be retried when it asks to be (admission full), and only then."""
import procrastinate

from app.vault_runtime.background_agent.jobs import RETRY, BackgroundJobs


def test_job_retry_is_honored_and_other_errors_fail():
    decision = procrastinate.RetryDecision(retry_in={"seconds": 2})
    retried = RETRY.get_retry_exception(procrastinate.exceptions.JobRetry(decision), job=None)
    assert isinstance(retried, procrastinate.exceptions.JobRetry)
    assert retried.retry_decision is decision
    assert RETRY.get_retry_exception(RuntimeError("boom"), job=None) is None


def test_work_task_carries_the_retry_strategy():
    jobs = BackgroundJobs(database_url="postgresql://unused/unused", executor=None)
    assert jobs._sync.tasks["vault.work"].retry_strategy is RETRY
